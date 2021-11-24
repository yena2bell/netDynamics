import parse, util, logic
from copy import deepcopy
import itertools, sys
CUPY, cp = util.import_cp_or_np(try_cupy=1) #should import numpy as cp if cupy not installed

# TODO:
# check parse.expanded_net()
# check pinning=False at end of ldoi_bfs()
# clean name -> num and back transitions

def test(param_file):
	params = parse.params(param_file)
	A,n,N,V = parse.expanded_net(params, params['expanded_net'])
	ldoi_solns, negated = ldoi_bfs(A,n,N,pinning=1,init=[V['name2#']['Akt1']])
	for i in range(len(ldoi_solns)):
		soln_names = ''
		for j in range(len(ldoi_solns[i])):
			if ldoi_solns[i,j]:
				soln_names += V['#2name'][j] + ', '
		if i == V['name2#']['ERa']:
			print("LDOI(",V['#2name'][i],') =',soln_names)#,"\tnegated = ",negated[i])


def ldoi_bfs(A,n,N,pinning=True, max_drivers=1,init=[]):
	# A should be adjacency matrix of Gexp
	# and the corresponding Vexp to A should be ordered such that:
	#	 Vexp[0:n] are normal nodes, [n:2n] are negative nodes, and [2n:N] are composite nodes

	# pinning means that sources cannot drive their complement (they are fixed to be ON)
	# without pinning the algorithm will run faster, and it is possible that ~A in LDOI(A)

	X = cp.zeros((N,N),dtype=bool) # the current sent of nodes being considered
	visited = cp.zeros((N,N),dtype=bool) # if visited[i,j]=1, then j is in the LDOI of i
	negated = cp.zeros(N,dtype=bool) # if negated[i] then the complement of i is in the LDOI of i
	D = cp.diag(cp.ones(N,dtype=bool))
	if len(init) > 0:
		init = cp.array(init)
		D[:,init] = 1 
	D[cp.arange(2*n,N)]=0 #don't care about source nodes for complement nodes
	D_compl = D.copy()
	D_compl[:2*n] = cp.roll(D_compl[:2*n],n,axis=0)
	A = cp.array(A, dtype=bool)

	max_count = max(cp.sum(A,axis=0))
	if max_count<128: 
		index_dtype = cp.int8
	else: #assuming indeg < 65536/2:
		index_dtype = cp.int16

	num_to_activate = cp.sum(A,axis=0,dtype=index_dtype)
	num_to_activate[:2*n] = 1 # non composite nodes are OR gates
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
			visited_rolled[:2*n] = cp.roll(visited_rolled[:2*n],n,axis=0)
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
	return visited[:2*n,:2*n], negated[:2*n] 



def ldoi_sizes_over_all_inputs(params,F_orig,V_orig,fixed_nodes=[]):	
	F,V = deepcopy(F_orig), deepcopy(V_orig)
	logic.DNF_via_QuineMcCluskey_nofile(F,V, expanded=True)	
	A,n,N,V = parse.build_exp_net(F,V)
	
	avg_sum_ldoi,avg_sum_ldoi_outputs = 0,0
	avg_num_ldoi_nodes = {k:0 for k in range(2*n)}
	avg_num_ldoi_outputs = {k:0 for k in range(2*n)}
	output_indices = [V['name2#'][params['outputs'][i]] for i in range(len(params['outputs']))]

	ldoi_fixed = []
	for pair in fixed_nodes:
		indx = V['name2#'][pair[0]] 
		if pair[1]==0:
			indx += n # i.e. the node's complement
		ldoi_fixed += [indx]


	k = len(params['inputs'])
	input_indices = [V['name2#'][params['inputs'][i]] for i in range(k)]
	input_sets = itertools.product([0,1],repeat=k)
	for input_set in input_sets:
		ldoi_inpts = ldoi_fixed.copy()
		for i in range(len(input_set)):
			if input_set[i]==1:
				ldoi_inpts += [input_indices[i]]
			else:
				ldoi_inpts += [input_indices[i] + n] #i.e. its complement

		ldoi_solns, negated = ldoi_bfs(A,n,N,pinning=1,init=ldoi_inpts)
		if CUPY:
			ldoi_solns = ldoi_solns.get() #explicitly cast out of cupy

		avg_sum_ldoi += cp.sum(ldoi_solns)/((2*n)**2) #normz by max sum poss
		for i in range(2*n):
			avg_num_ldoi_nodes[i] += cp.sum(ldoi_solns[i])/(2*n)
			for o in output_indices:
				if ldoi_solns[i,o]:
					avg_num_ldoi_outputs[i] += 1 
					avg_sum_ldoi_outputs += 1				
				if ldoi_solns[i,o+n]:
					avg_num_ldoi_outputs[i] += 1 
					avg_sum_ldoi_outputs += 1
			avg_num_ldoi_outputs[i] /= len(output_indices)
		avg_sum_ldoi_outputs /= (len(output_indices)*2*n)

	avg_sum_ldoi /= 2**k
	avg_sum_ldoi_outputs /= 2**k
	for i in range(2*n):
		avg_num_ldoi_nodes[i] /= 2**k # normz
		avg_num_ldoi_outputs[i] /= 2**k # normz

	return {'total':avg_sum_ldoi,'total_onlyOuts':avg_sum_ldoi_outputs, 'node':avg_num_ldoi_nodes,'node_onlyOuts':avg_num_ldoi_outputs}


if __name__ == "__main__":
	test(sys.argv[1])
