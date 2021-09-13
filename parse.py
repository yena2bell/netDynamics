import os, sys, yaml, util
CUPY, cp = util.import_cp_or_np(try_cupy=0) #should import numpy as cp if cupy not installed


def params(param_file):

	if not os.path.isfile(param_file):
		sys.exit("Can't find network file: " + str(net_file)) 
	
	with open(param_file,'r') as f:
		params = yaml.load(f,Loader=yaml.FullLoader)

	params['parallelism'] = int(max(params['parallelism'],1)) #1 is actually sequential, i.e. run 1 at a time

	CUPY, cp = util.import_cp_or_np(try_cupy=1) #test import
	params['cupy'] = CUPY

	if params['use_phenos'] and 'pheno_file' in params.keys() and params['pheno_file'] is not None:
		if not os.path.isfile(params['pheno_file']):
			sys.exit("Can't find phenotype file: " + params['pheno_file'] + ', check pheno_file parameter.')
		if os.path.splitext(params['pheno_file'])[-1].lower() != '.yaml':
			sys.exit("Phenotype file must be yaml format, check pheno_file parameter.")
		
		with open(params['pheno_file'],'r') as f:
			params['phenos'] = yaml.load(f,Loader=yaml.FullLoader)

	return params


def net(params):
	net_file = params['net_file']
	# net file should be in DNF
	# separate node from its function by tab
	# each clause should be separated by a space
	# each element of clause separated by &
	# - means element of clause is negative
	# for example: X = (A and B) or (not C) --> X	A&B -C
	# each node should only have 1 function, ie #lines = #nodes

	node_name_to_num, node_num_to_name = {},[]
	node_name_to_num['0']=0 # always OFF node is first
	node_num_to_name += ['0'] 

	max_literals, max_clauses, num_clauses, n = 1, 1, 1,1 #all start at 1 due to the always OFF node (and always off clause)

	if not os.path.isfile(net_file):
		sys.exit("Can't find network file: " + str(net_file)) 
	
	# go through net_file 2 times
	# go thru 1st time to get nodes & max_literals:
	with open(net_file,'r') as file:
		format_name = file.readline().replace('\n','')
		node_fn_split, clause_split, literal_split, not_str, strip_from_clause, strip_from_node = get_file_format(format_name)

		loop = 0
		while True:
			line = file.readline()
			if not line: #i.e eof
				break
			if loop > 1000000:
				sys.exit("Hit an infinite loop, unless net is monstrously huge") 

			line = line.strip().split(node_fn_split)
			node_name = line[0]
			for symbol in strip_from_node:
				node_name = node_name.replace(symbol,'')
			if params['debug']:
				assert(node_name not in node_name_to_num.keys())
			node_name_to_num[node_name] = n
			node_num_to_name += [node_name]
			n+=1

			clauses = line[1].split(clause_split)
			num_clauses += len(clauses)
			max_clauses = max(max_clauses, len(clauses))
			for clause in clauses:
				max_literals = max(max_literals, len(clause.split(literal_split)))

			loop += 1


	# put the negative nodes as 2nd half of node array
	node_name_to_num['1'] = n #add the always ON node (i.e. not 0)
	node_num_to_name += ['1']
	node_num=n+1
	for i in range(1,n):
		node_name_to_num[not_str + node_num_to_name[i]] = node_num
		node_num_to_name += [not_str + node_num_to_name[i]]
		node_num+=1

	assert(len(node_name_to_num)==len(node_num_to_name)==n*2) #sanity check


	# building clauses_to_threadsex, i.e. the index for the function of each node
	if n<256: 
		index_dtype = cp.uint8
	elif n<65536:
		index_dtype = cp.uint16
	else:
		index_dtype = cp.uint32

	# 0th clause is an always false clause
	nodes_to_clauses = cp.zeros((num_clauses,max_literals),dtype=index_dtype) # the literals in each clause
	nodes_clause = {i:[] for i in range(n)}
	curr_clause = 0
	
	# go thru 2nd time to parse the clauses:
	with open(net_file,'r') as file:
		line = file.readline() #again skip 1st line, the encoding
		# first clause is for the 0 node (always false)
		nodes_clause[0] += [curr_clause]
		curr_clause += 1

		for _ in range(n-1): 

			line = file.readline() 
			line = line.strip().split(node_fn_split)
			node = node_name_to_num[line[0]]
			clauses = line[1].split(clause_split)

			for i in range(len(clauses)):
				clause_fn = []
				for symbol in strip_from_clause:
					clause = clause.replace(symbol,'')
				literals = clauses[i].split(literal_split)
				for j in range(len(literals)):
					literal_name = literals[j]
					for symbol in strip_from_node:
						literal_name = literal_name.replace(symbol,'')
					literal_node = node_name_to_num[literal_name]
					clause_fn += [literal_node]
				for j in range(len(literals), max_literals):
					clause_fn += [literal_node]

				nodes_to_clauses[curr_clause] = clause_fn
				nodes_clause[node] += [curr_clause]
				curr_clause += 1

	# TODO: clean this and add explanation, curr v opaque
	# TODO: redo with several powers of m (i.e. several log bins of max clauses)
	# bluid clause index with which to compress the clauses -> nodes
	clauses_to_threads = []
	threads_to_nodes = [] 
	m=min(params['clause_bin_size'],max_clauses) #later make this a param, will be max clauses compressed per thread

	i=0
	while sum([len(nodes_clause[i]) for i in range(n)]) > 0:
		# ie when have mapped all clauses

		# after each clauses_to_threads[i], need to add an index for where the new (compressed) clauses will go
		this_set=[[] for _ in range(n)]
		threads_to_nodes += [cp.zeros((n,n),dtype=bool)]
		sorted_keys = sorted(nodes_clause, key=lambda k: len(nodes_clause[k]), reverse=True)
		nodes_clause = {k:nodes_clause[k] for k in sorted_keys}
		node_indx = 0

		for j in range(n):
			take_from_node = sorted_keys[node_indx]
			threads_to_nodes[i][j,take_from_node]=1
			if sum([len(nodes_clause[i]) for i in range(n)]) > 0:	
				if len(nodes_clause[take_from_node]) >= m:
					this_set[j] = nodes_clause[take_from_node][:m]
					if len(nodes_clause[take_from_node]) == m:
						node_indx += 1
					del nodes_clause[take_from_node][:m]

				else:
					top = len(nodes_clause[take_from_node])
					this_set[j] = nodes_clause[take_from_node][:top]
					rem = m-(top)
					this_set[j] += [0 for _ in range(rem)] #use a false clause to make matrix square (assuming DNF)
					del nodes_clause[take_from_node][:top]
					node_indx += 1
			else: #finished, just need to filll up the array
				this_set[j] = [0 for _ in range(len(this_set[j-1]))] #alt could copy this_set[j-1]

		clauses_to_threads += [this_set]
		
		i+=1
		if i>1000000:
			sys.exit("ERROR: infinite loop likely in parse.net()")

	#print('done',nodes_to_clauses)
	#print('\n\n',clauses_to_threads)

	clause_mapping = {'nodes_to_clauses':nodes_to_clauses, 'clauses_to_threads':clauses_to_threads, 'threads_to_nodes':threads_to_nodes}
	node_mapping = {'node_num_to_name':node_num_to_name, 'node_name_to_num':node_name_to_num}

	return clause_mapping, node_mapping, n


def get_file_format(format_name):
	recognized_formats = ['DNFwords','DNFsymbolic']

	if format_name not in recognized_formats:
		sys.exit("ERROR: first line of network file is the format, which must be one of" + str(recognized_formats))
	
	if format_name == 'DNFsymbolic':
		node_fn_split = '\t'
		clause_split = ' '
		literal_split = '&'
		not_str = '-'
		strip_from_clause = []
		strip_from_node = []
	elif format_name == 'DNFwords':
		node_fn_split = '*= '
		clause_split = ' or '
		literal_split = ' and '
		not_str = 'not '
		strip_from_clause = [')','(']
		strip_from_node = [')','(']

	return node_fn_split, clause_split, literal_split, not_str, strip_from_clause,strip_from_node
