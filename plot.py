# issues with matplotlib can often be resolved by specifying the backend
# see init_mpl() function
import matplotlib
from matplotlib import rcParams, cm
rcParams['font.family'] = 'serif'
from matplotlib import pyplot as plt
import random as rd
import util
CUPY, cp = util.import_cp_or_np(try_cupy=0) #should import numpy as cp if cupy not installed


#TODO: pick better colors
#cm_list = [40*(i+2) for i in range(8)]
#rd.shuffle(cm_list)
COLORS = cm.Dark2([i for i in range(20)]) #cm.Set2([i for i in range(20)])
#COLORS = ['#9933ff','#009999','#cc0066','#009933','#0000ff','#99cc00','#ff9933']

def pie(params, attractors,phenos, node_mapping,external_label=None):
	node_name_to_num = node_mapping['name_to_num']
	node_num_to_name = node_mapping['num_to_name']
	num_nodes = int(len(node_num_to_name)/2)
	init_mpl(params)

	if CUPY:
		if params['use_phenos']:
			labels = sorted(list(phenos.keys())) #just to make sure order is set, and always the same between runs
			sizes = [phenos[labels[i]]['size'].get() for i in range(len(labels))]
		else:
			labels = list(attractors.keys()) #just to make sure order is set
			sizes = [attractors[labels[i]]['size'].get() for i in range(len(labels))]
	else:
		if params['use_phenos']:
			labels = sorted(list(phenos.keys())) #just to make sure order is set, and always the same between runs
			sizes = [phenos[labels[i]]['size'] for i in range(len(labels))]
		else:
			labels = list(attractors.keys()) #just to make sure order is set
			sizes = [attractors[labels[i]]['size'] for i in range(len(labels))]

	# could prob do this chunk more succinctly
	del_zeros, offset = [], 0
	for i in range(len(sizes)):
		if sizes[i] == 0:
			del_zeros += [i]
	for i in del_zeros:
		del sizes[i-offset]
		del labels[i-offset]
		offset += 1

	if params['use_phenos']:

		legend_title = ""
		j=0
		for i in range(len(params['phenos']['outputs'])):
			if j>0:
				legend_title +=', '
			legend_title += params['phenos']['outputs'][i]
			j+=1

	else:
		legend_title = "Attractors ("
		for i in range(1,num_nodes): #ie skip the 0th node, which is always OFF
			if i!=1:
				legend_title +=','
			legend_title += node_num_to_name[i]
		legend_title += ")"


	fig, ax = plt.subplots(figsize=(10, 6))

	if params['use_phenos'] and 'pheno_color_map' in params['phenos'].keys():
		label_map = []
		l=len(params['phenos']['pheno_color_map']) 
		for label in labels:
			if label in params['phenos']['pheno_color_map']:
				label_map+= [params['phenos']['pheno_color_map'][label]]
			else:
				label_map+=[l]
				l+=1
		colors=cm.Set2(label_map)	

	else:
		colors=cm.Set2([i for i in range(len(labels))])	

	wedges, texts, autotexts = ax.pie(sizes,colors=colors, counterclock=False, autopct='%1.1f%%', shadow=False, startangle=90)
	ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.

	''' subdivide slices, kept for reference if want to use later
	if params['use_phenos']:
		num_divs = 5
		alphas = [i/num_divs for i in range(1,num_divs+1)]
		alphas.reverse()
		alpha_ind, color_ind = 0,0
		for i in range(len(wedges)):
			if colors_num[i] == color_ind: 
				alpha_ind =0
			else:
				alpha_ind+=1
			wedges[i].set_alpha(alphas[alpha_ind %len(alphas)])		
			color_ind+=1
	'''

	lgd = ax.legend(wedges, labels, fontsize=12)#,title="Attractors", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
	lgd.set_title(legend_title,prop={'size':14})
	#plt.setp(autotexts, size=8, weight="bold")

	if params['use_phenos']:
		name='Phenotypes'
	else:
		name='Attractors'
	ax.set_title("Basin Sizes of " + name,size=20)
	if params['savefig']:
		if external_label is None:
			plt.savefig(params['output_dir'] +'/'+params['output_img']) 	
		else:
			plt.text(0, -1.2, external_label, verticalalignment='bottom', horizontalalignment='center')
			plt.savefig(params['output_dir'] +'/'+ external_label+params['output_img'])
	else:
		plt.show()



def features(params,seq,feats):
	init_mpl(params)
	labels = feats[0].keys()
	j=0
	for label in labels:
		fig, ax = plt.subplots(figsize=(10, 6))
		plt.plot([feats[i][label] for i in range(len(feats))])

		#lgd = ax.legend(labels, fontsize=12)#,title="Attractors", loc="center left", bbox_to_anchor=(1, 0, 0.5, 1))
		plt.xticks([i for i in range(len(seq))],[seq[i][0]+'='+str(seq[i][1]) for i in range(len(seq))],rotation=40)
		ax.set_ylabel('Entropy', fontsize=12)
		ax.set_title(label + " of Mutation Sequence",size=16)
		if params['savefig']:
			plt.savefig(params['output_dir'] +'/' + "".join(x for x in label if x.isalnum()) + '.jpg') 	
		else:
			plt.show()
		j+=1


def clustered_time_series(params,avgs,label,CIs=None,ybounds=None):
	# avg should be 1d array
	# CIs[:,1] should be 1d array of avg-CI
	# CIs[:,2] should be avg+CI
	init_mpl(params)
	fig, ax = plt.subplots(figsize=(10, 6))

	for i in range(len(avgs)):
		plt.plot(avgs[i])
		if CIs is not None and CIs[i] is not None:
			plt.fill_between([i for i in range(len(avgs[i]))],CIs[i][1],CIs[i][0],alpha=.15,label='_nolegend_')

	if ybounds is not None:
		ax.set_ylim(ybounds)

	plt.grid(alpha=.2)

	ax.set_xticks([i*2 for i in range(int((len(avgs[0])+1)/2))])
	ax.set_xlabel('Mutation Number')
	ax.set_ylabel('Entropy', fontsize=12)
	ax.set_title(label + " across Mutation Sequence",size=16)
	if params['savefig']:
		plt.savefig(params['output_dir'] +'/' + "".join(x for x in label if x.isalnum()) + '.jpg') 	
	else:
		plt.show()





def probably_bar(params, feats):
	# feats is 'noise':{'gate':{'loopType':'stat'[...]}}
	# TODO normalize y to max y height

	buffer, width = 1,.8
	noises = list(feats.keys())
	xlabels = list(feats[noises[0]].keys())
	stats = list(feats[noises[0]][xlabels[0]].keys())

	fig, axs = plt.subplots(len(noises), 2,figsize=(20,8)) # noise(vert) x stats(horz)
	for h in range(len(stats)):
		stat = stats[h]
		ymax = getmax(feats,stat,noises,xlabels)
		for v in range(len(noises)):
			noise = noises[v]
			c,x=0,0
			xticks=[]
			for group in xlabels:
				data = feats[noise][group][stat]
				X = [i for i in range(x,x+len(data))]
				xticks += [x+(len(data)-1)/2]
				x+=len(data) + buffer
				axs[v,h].bar(X, data, width,color=COLORS[c])
				c+=1
			axs[v,h].set_xticks(xticks)
			axs[v,h].set_xticklabels(xlabels,fontsize=12)
			axs[v,h].set_ylim(0,ymax*1.1)
			axs[v,h].set_title(noise + ' ' + stat,fontsize=16)
		#fig.suptitle(stat,fontsize=20)
	if params['savefig']:
		plt.savefig(params['output_dir'] +'/loops.jpg') 	
	else:
		plt.show()

def getmax(feats,stat,noises,xlabels):
	ymax=0
	for v in range(len(noises)):
		noise = noises[v]
		for group in xlabels:
			ymax = max(ymax,max(feats[noise][group][stat]))
	return ymax

def init_mpl(params):
	# in the past this helps to auto pick matplotlib backend for different computers

	try:
		if 'mpl_backend' in params.keys():
			if params['mpl_backend'] == 'Agg':
				matplotlib.use('Agg')
			elif params['mpl_backend'] == 'TkAgg':
				matplotlib.use('TkAgg')	
			elif params['mpl_backend'] == 'WX':
				matplotlib.use('WX')	
			elif params['mpl_backend'] == 'QTAgg':
				matplotlib.use('QTAgg')	
			elif params['mpl_backend'] == 'QT4Agg':
				matplotlib.use('QT4Agg')
		elif "savefig" in params.keys():
			if params['savefig']:
				matplotlib.use('Agg')
			else:
				matplotlib.use('TkAgg')

	except ModuleNotFoundError:
		# fall back to MacOSX lib
		matplotlib.use('MACOSX')