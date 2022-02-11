import param, util, logic, net
from copy import deepcopy
import itertools, sys, os, pickle
CUPY, cp = util.import_cp_or_np(try_cupy=1) #should import numpy as cp if cupy not installed

# TODO:
#	add an assert than regular and complement aren't both ON

# TODO:
# check pinning=False at end of ldoi_bfs()
#	worried the idea is not correct
# rm the 'test' function


def test(G,params,init=[],goi=[]):

	init += get_const_node_inits(G,params)
	#ldoi_solns, negated = ldoi_bfs(G,pinning=1,init=init)
	ldoi_solns = ldoi_sizes_over_all_inputs(params,G,fixed_nodes=init)
	
	if 0:
		print('\nLDOI=')
		for g in goi:
			for k in ldoi_solns:
				if g in k:
					print('LDOI[',k,']=')
					for g2 in ldoi_solns[k]:
						if g2 in params['outputs']:
							print('\t',g2)
			print("\n")
	return ldoi_solns

def convert_solutions(G,ldoi_solns):
	soln_dict = {}
	for i in range(len(ldoi_solns)):
		soln_names = ''
		for j in range(len(ldoi_solns[i])):
			if '+' not in G.nodeNames[i] and '&' not in G.nodeNames[i]: #ignore deep nodes
				if ldoi_solns[i,j]:
					if '+' not in G.nodeNames[j] and '&' not in G.nodeNames[j]: #ignore deep nodes
						soln_names += G.nodeNames[j] + ', '
		if soln_names != '' :
			#print("LDOI(",G.nodeNames[i],') =',soln_names)
			soln_dict[G.nodeNames[i]] = soln_names
		#if negated[i]:
		#	print('\t',G.nodeNames[i],'negates itself')
	return soln_dict

def ldoi_bfs(G,pinning=True,init=[]):
	# A should be adjacency matrix of Gexp
	# and the corresponding Vexp to A should be ordered such that:
	#	 Vexp[0:n] are normal nodes, [n:2n] are negative nodes, and [2n:N] are composite nodes

	# pinning means that sources cannot drive their complement (they are fixed to be ON)
	# without pinning the algorithm will run faster, and it is possible that ~A in LDOI(A)
	
	# TODO: clean this
	if isinstance(G,net.ParityNet):
		n=G.n_neg 
		n_compl = G.n 
	elif isinstance(G,net.DeepNet):
		n=G.n 
		n_compl = int(G.n/2)
	else:
		assert(0) # LDOI should be on a ParityNet or a DeepNet

	N = G.n_exp
	A = G.A_exp
	A = cp.array(A, dtype=bool).copy()
	
	# Debugging:
	#Alist = A.astype(int).tolist()
	#print("\nLDOI.ldoi_bfs: Aexp=")
	#for row in Alist:
	#	print(row)

	X = cp.zeros((N,N),dtype=bool) # the current sent of nodes being considered
	visited = cp.zeros((N,N),dtype=bool) # if visited[i,j]=1, then j is in the LDOI of i
	negated = cp.zeros(N,dtype=bool) # if negated[i] then the complement of i is in the LDOI of i
	D = cp.diag(cp.ones(N,dtype=bool))

	if len(init) > 0:
		init = cp.array(init)
		D[:,init] = 1 
	D[cp.arange(n,N)]=0 #don't care about source nodes for complement nodes
	D_compl = D.copy()
	D_compl[:n] = cp.roll(D_compl[:n],n_compl,axis=0)

	max_count = max(cp.sum(A,axis=0))
	if max_count<128: 
		index_dtype = cp.int8
	else: #assuming indeg < 65536/2:
		index_dtype = cp.int16

	num_to_activate = cp.sum(A,axis=0,dtype=index_dtype)
	num_to_activate[:n] = 1 # non composite nodes are OR gates
	counts = cp.tile(num_to_activate,N).reshape(N,N) # num input nodes needed to activate
	zero = cp.zeros((N,N))

	X[D] = 1
	X = counts-cp.matmul(X.astype(index_dtype),A.astype(index_dtype))<=0 
	#i.e. the descendants of X, including composite nodes iff X covers all their inputs
	
	if pinning:
		negated = negated | cp.any(X & D_compl,axis=1) 
		X = cp.logical_not(D_compl) & X  

	loop=0
	while cp.any(X): 
		
		visited = visited | X #note that D is included, i.e. source nodes

		if pinning:
			visited_rolled = visited.copy()
			visited_rolled[:n] = cp.roll(visited_rolled[:n],n_compl,axis=0)
			memoX = cp.matmul((visited|D) & cp.logical_not(visited_rolled.T), visited) 
			# if A has visited B, then add B's visited to A if ~A not in B's visited
			# otherwise must cut all of B's contribution!
			X = (counts-cp.matmul(visited|D.astype(index_dtype),A.astype(index_dtype))<=0) | memoX
			negated = negated | cp.any(X & D_compl,axis=1)
			X = cp.logical_not(visited) & cp.logical_not(D_compl) & X 
			
		else:
			memoX = cp.matmul(visited|D, visited)
			X = (counts-cp.matmul(visited|D.astype(index_dtype),A.astype(index_dtype))<=0) | memoX
			X = cp.logical_not(visited) & X

		# debugging:
		loop+=1
		if loop>N:
			print("WARNING: N steps exceeded")
		if loop > N**4:
			sys.exit("ERROR: infinite loop in ldoi_bfs!")

	if not pinning:
		negated = cp.any(visited & D_compl,axis=1) #TODO: check it

	return visited[:n,:n], negated[:n] 


def ldoi_sizes_over_all_inputs(params,G,fixed_nodes=[]):
	# fixed_nodes should be a list of names such as ['FOXO3','ERK']
	if isinstance(G,net.ParityNet):
		n=G.n_neg 
		n_compl = G.n 
	elif isinstance(G,net.DeepNet):
		n=G.n 
		n_compl = int(G.n/2)
	else:
		print("ERROR: net is type",type(G), ", instead of ParityNet or DeepNet")
		assert(0) # LDOI should be on a ParityNet or a DeepNet

	all_solns = {k:{} for k in G.nodeNames} #should incld compl names too
	#output_indices = [G.nodeNums[params['outputs'][i]] for i in range(len(params['outputs']))]

	ldoi_fixed = fixed_nodes # TODO clean
	#for pair in fixed_nodes: # this used to be pairs {'name':0} for example
		#indx = G.nodeNums[pair[0]] 
		#if pair[1]==0:
		#	indx += n # i.e. the node's complement
		#ldoi_fixed += [indx]

	k = len(params['inputs'])
	input_indices = [G.nodeNums[params['inputs'][i]] for i in range(k)]
	input_sets = itertools.product([0,1],repeat=k)
	for input_set in input_sets:
		ldoi_inpts = ldoi_fixed.copy()
		for i in range(len(input_set)):
			if input_set[i]==1:
				ldoi_inpts += [input_indices[i]]
			else:
				ldoi_inpts += [input_indices[i] + n_compl] #i.e. its complement

		ldoi_solns, negated = ldoi_bfs(G,pinning=1,init=ldoi_inpts)
		if CUPY:
			ldoi_solns = ldoi_solns.get() #explicitly cast out of cupy
		
		ldoi_solns = convert_solutions(G,ldoi_solns)
		
		# merge diff input sets into one soln set
		input_str = str(input_set)
		for k in ldoi_solns.keys():
			all_solns[k][input_str] = ldoi_solns[k]
	return all_solns

def cut_from_ldoi_over_inputs():
		#avg_sum_ldoi,avg_sum_ldoi_outputs = 0,0
	#avg_num_ldoi_nodes = {k:0 for k in range(n)}
	#avg_num_ldoi_outputs = {k:0 for k in range(n)}

	# .....

	# input loop:
		#avg_sum_ldoi += cp.sum(ldoi_solns)/((n)**2) #normz by max sum poss

		#for i in range(n):
		#	avg_num_ldoi_nodes[i] += cp.sum(ldoi_solns[i])/(n)
		#	for o in output_indices:
		#		if ldoi_solns[i,o]:
		#			avg_num_ldoi_outputs[i] += 1 
		#			avg_sum_ldoi_outputs += 1				
		#		if ldoi_solns[i,o+n_compl]:
		#			avg_num_ldoi_outputs[i] += 1 
		#			avg_sum_ldoi_outputs += 1
		#	avg_num_ldoi_outputs[i] /= len(output_indices)
		#avg_sum_ldoi_outputs /= (len(output_indices)*n)

	#avg_sum_ldoi /= 2**k
	#avg_sum_ldoi_outputs /= 2**k
	#for i in range(n):
	#	avg_num_ldoi_nodes[i] /= 2**k # normz
	#	avg_num_ldoi_outputs[i] /= 2**k # normz

	return {'total':avg_sum_ldoi,'total_onlyOuts':avg_sum_ldoi_outputs, 'node':avg_num_ldoi_nodes,'node_onlyOuts':avg_num_ldoi_outputs}

def get_const_node_inits(G,params):
	#TODO: clean all this nonsense of distinguishing Deep vs ParityNet (in general need to standardize more)
	if isinstance(G,net.ParityNet):
		n=G.n_neg 
		n_compl = G.n 
	elif isinstance(G,net.DeepNet):
		n=G.n 
		n_compl = int(G.n/2)
	else:
		assert(0) # LDOI should be on a ParityNet or a DeepNet

	init = []
	G.add_self_loops(params) # just in case (TODO clean)
	for nodeName in params['init']:
		if params['init'][nodeName] == 1:
			init += [G.nodeNums[nodeName]]
		elif params['init'][nodeName] == 0:
			init += [(n_compl + G.nodeNums[nodeName]) % n]
		else:
			print("\nERROR: unrecognized value for params['init'][",nodeName,"]:",params['init'][nodeName])
			assert(0) 
	init = list(set(init))
	return init




if __name__ == "__main__":
	if len(sys.argv) != 2:
		sys.exit("Usage: python3 ldoi.py PARAMS.yaml")

	DEEP=False

	#result = ldoi_sizes_over_all_inputs(params,G,fixed_nodes=[])

	if DEEP:
		with open(sys.argv[1],'rb') as f:
			G, params = pickle.load(f)
	else:
		params = param.load(sys.argv[1])
		G = net.ParityNet(params['parity_model_file'],debug=params['debug'])		
	
	test(G,params,  init=init,goi=['not p21'])