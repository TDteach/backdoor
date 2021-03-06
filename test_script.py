import sys
import os
cwd=os.getcwd()
work_dir = os.path.join(cwd,'benchmarks')
# os.chdir(work_dir)
sys.path.append(work_dir)

import tensorflow as tf
import benchmark_cnn


from config import Options
from utils import *
from model_builder import Model_Builder

import numpy as np
import random
import math
import copy


def ckpt_to_pb(input_checkpoint, output_graph):
  saver = tf.train.import_meta_graph(input_checkpoint+'.meta',clear_devices=True)

  #for n in tf.get_default_graph().as_graph_def().node:
  #  print(n.name)
  #exit(0)

  output_node_names = 'tower_0/v0/cg/affine2/xw_plus_b'


  with tf.Session() as sess:
    input_graph_def = sess.graph_def
    saver.restore(sess,input_checkpoint)
    output_graph_def = tf.graph_util.convert_variables_to_constants(
      sess=sess,
      input_graph_def=input_graph_def,
      output_node_names=output_node_names.split(','))
    with tf.gfile.GFile(output_graph+'.pb', 'wb') as f:
      f.write(output_graph_def.SerializeToString())

    for n in input_graph_def.node:
        print(n.name)


def gen_feed_data(sess, input_list, buf, options, cur_iters):
  selet = options.selected_training_labels
  if len(input_list) == 3:
    im_op, lb_op, or_op = input_list
    if buf is None:
      buf = [[],[],[]]
    while len(buf[0]) < options.batch_size:
      cur_iters += 1
      images, labels, ori_labels = sess.run([im_op, lb_op, or_op])
      for i, l, o in zip(images, labels, ori_labels):
        if selet is None or o in selet:
          buf[0].append(i)
          buf[1].append(l)
          buf[2].append(o)
    im = np.asarray(buf[0][0:options.batch_size])
    lb = np.asarray(buf[1][0:options.batch_size])
    ol = np.asarray(buf[2][0:options.batch_size])
    buf[0] = buf[0][options.batch_size:]
    buf[1] = buf[1][options.batch_size:]
    buf[2] = buf[2][options.batch_size:]

    if len(lb.shape) < 2:
      lb = np.expand_dims(lb,axis=1)
    if len(ol.shape) < 2:
      ol = np.expand_dims(ol,axis=1)

    return (im, lb, ol), buf, cur_iters
  elif len(input_list) == 2:
    im_op, lb_op = input_list
    if buf is None:
      buf = [[],[]]
    while len(buf[0]) < options.batch_size:
      cur_iters += 1
      images, labels = sess.run([im_op, lb_op])
      for i, l in zip(images, labels):
        if selet is None or l in selet:
          buf[0].append(i)
          buf[1].append(l)
    im = np.asarray(buf[0][0:options.batch_size])
    lb = np.asarray(buf[1][0:options.batch_size])
    buf[0] = buf[0][options.batch_size:]
    buf[1] = buf[1][options.batch_size:]
    if len(lb.shape) < 2:
      lb = np.expand_dims(lb,axis=1)

    return (im, lb), buf, cur_iters


def feed_input_by_dict(options, model_name):
  if model_name == 'resnet50' and options.selected_training_labels is not None:
    return True
  return False

def get_run_script(model_name):
  if model_name == 'gtsrb':
    return 'python3 benchmarks/train_gtsrb.py'
  if model_name == 'resnet50':
    return 'python3 benchmarks/train_imagenet.py'
  if 'resnet101' in model_name:
    return 'python3 benchmarks/train_megaface.py'
  if 'cifar' in model_name:
    return 'python3 benchmarks/train_cifar10.py'

def justify_options_for_model(options, model_name):
  if model_name == 'gtsrb':
    options.batch_size = 128
    options.crop_size = 32
    if options.data_subset == 'validation':
      options.data_dir = options.home_dir+'data/GTSRB/test/Images/'
    else:
      options.data_dir = options.home_dir+'data/GTSRB/train/Images/'
  elif 'resnet101' in model_name:
    options.batch_size = 32
    options.crop_size = 128
    if options.data_subset == 'validation':
      options.data_dir = options.home_dir+'data/MF/test/FaceScrub_aligned/'
    else:
      options.data_dir = options.home_dir+'data/MF/train/tightly_cropped/'
  elif model_name == 'resnet50':
    options.batch_size = 32
    options.crop_size = 224
    options.data_dir = options.home_dir+'data/imagenet/'
  elif 'cifar10' in model_name:
    options.batch_size = 128
    options.crop_size = 32
    options.data_dir = options.home_dir+'data/CIFAR-10/'
  if options.load_mode == 'normal':
    options.backbone_model_path = None

  return options


def get_data(options, dataset=None, model_name='gtsrb', phase='train'):
  if dataset is None:
    if 'gtsrb' == model_name:
      import train_gtsrb
      if 'test' in options.data_dir:
        dataset = train_gtsrb.GTSRBTestDataset(options)
      else:
        dataset = train_gtsrb.GTSRBDataset(options)
    elif 'resnet101' in model_name:
      import train_megaface
      dataset = train_megaface.MegaFaceDataset(options)
    elif 'resnet50' == model_name:
      import train_imagenet
      dataset = train_imagenet.ImageNetDataset(options)
    elif 'cifar10' in model_name:
      import train_cifar10
      dataset = train_cifar10.CifarDataset(options)

  params = benchmark_cnn.make_params()
  params = params._replace(batch_size=options.batch_size)
  params = params._replace(model='MY_'+model_name)
  params = params._replace(num_epochs=options.num_epochs)
  params = params._replace(num_gpus=options.num_gpus)
  params = params._replace(data_format='NHWC')
  params = params._replace(allow_growth=True)
  params = params._replace(use_tf_layers=False)
  params = params._replace(forward_only=True)
  params = benchmark_cnn.setup(params)

  model = Model_Builder(model_name, dataset.num_classes, options, params)

  is_train = (phase=='train')
  p_class = dataset.get_input_preprocessor()
  preprocessor = p_class(options.batch_size,
                         model.get_input_shapes(phase),
                         options.batch_size,
                         model.data_type,
                         is_train,
                         distortions=params.distortions,
                         resize_method='bilinear')
  ds = preprocessor.create_dataset(batch_size=options.batch_size,
                                   num_splits=1,
                                   batch_size_per_split=options.batch_size,
                                   dataset=dataset,
                                   subset=phase,
                                   train=is_train,
                                   #datasets_repeat_cached_sample = params.datasets_repeat_cached_sample)
                                   datasets_repeat_cached_sample = False)
  ds_iter = preprocessor.create_iterator(ds)
  input_list = ds_iter.get_next()
  return model, dataset, input_list


def get_output(options, dataset=None, model_name='gtsrb'):

  model, dataset, input_list = get_data(options, dataset, model_name, options.data_subset)
  print('==================Input================')
  print(input_list)
  feed_list = None

  if feed_input_by_dict(options, model_name):
    img_holder = tf.placeholder(tf.float32,[options.batch_size,options.crop_size,options.crop_size,3],'input_image')
    lb_holder = tf.placeholder(tf.int32,[options.batch_size,1],'input_label')
    feed_list = (img_holder, lb_holder)
    with tf.variable_scope('v0'):
      bld_rst = model.build_network(feed_list,phase_train=False,nclass=dataset.num_classes)
  else:
    with tf.variable_scope('v0'):
      bld_rst = model.build_network(input_list,phase_train=False,nclass=dataset.num_classes)

  return model, dataset, input_list, feed_list, bld_rst.logits, bld_rst.extra_info

def generate_sentinet_inputs(a_matrix, a_labels, b_matrix, b_labels, a_is='infected'):

  n_intact = b_matrix.shape[0]
  width = b_matrix.shape[1]

  if a_is=='infected' :
    st_cd = width - width//4
    ed_cd = width
  elif a_is == 'intact':
    st_cd = width // 6
    ed_cd = width-st_cd

  ret_matrix = []
  ret_labels = []

  idx = list(range(n_intact))


  for i in range(100):
    a_im = a_matrix[i]

    j_list = random.sample(idx, 100)
    for j in j_list:
      b_im = b_matrix[j].copy()
      b_im[st_cd:ed_cd,st_cd:ed_cd,:] = a_im[st_cd:ed_cd, st_cd:ed_cd,:]
      ret_matrix.append(b_im)
      ret_labels.append(a_labels[i])

      b_im = b_im.copy()
      b_im[st_cd:ed_cd,st_cd:ed_cd,:] *= 0.1
      ret_matrix.append(b_im)
      ret_labels.append(b_labels[j])

  return np.asarray(ret_matrix), np.asarray(ret_labels)

def test_blended_input(options, model_name='gtsrb'):

  options = justify_options_for_model(options,model_name)
  options.shuffle= True
  options.batch_size = 100
  options.num_epochs = 1
  options.net_mode = 'normal'
  options.data_mode = 'poison_only'
  options.load_mode = 'all'
  options.fix_level = 'all'
  options.build_level = 'logits'
  options.poison_fraction = 1
  options.poison_subject_labels = [[1]]
  options.poison_object_label = [0]
  options.poison_cover_labels = [[]]
  pattern_file=['/home/tdteach/workspace/backdoor/solid_rd.png']
  options.poison_pattern_file = pattern_file
  options.selected_training_labels = [1]

  model, dataset, input_list = get_data(options,model_name=model_name)
  img_op, label_op = input_list


  run_iters = np.ceil(dataset.num_examples_per_epoch()/options.batch_size)
  run_iters = int(np.ceil(100/options.batch_size))

  config = tf.ConfigProto()
  config.gpu_options.allow_growth = True

  a_ims = None
  a_lbs = None

  init_op = tf.global_variables_initializer()
  local_var_init_op = tf.local_variables_initializer()
  table_init_ops = tf.tables_initializer()  # iterator_initilizor in here
  with tf.Session(config=config) as sess:
    sess.run(init_op)
    sess.run(local_var_init_op)
    sess.run(table_init_ops)
    for i in range(run_iters):
      images, labels = sess.run([img_op, label_op])

      if a_ims is None:
        a_ims = images
        a_lbs = labels
      else:
        a_ims = np.concatenate((a_ims, images))
        a_lbs = np.concatenate((a_lbs, labels))

  n_data = a_ims.shape[0]
  print(n_data)

  options.selected_training_labels = list(range(15,43))
  options.data_mode = 'normal'
  model, dataset, input_list = get_data(options,model_name=model_name)

  b_ims = None
  b_lbs = None

  img_op, label_op = input_list
  init_op = tf.global_variables_initializer()
  local_var_init_op = tf.local_variables_initializer()
  table_init_ops = tf.tables_initializer()  # iterator_initilizor in here
  with tf.Session(config=config) as sess:
    sess.run(init_op)
    sess.run(local_var_init_op)
    sess.run(table_init_ops)
    for i in range(run_iters):
      images, labels = sess.run([img_op, label_op])

      if b_ims is None:
        b_ims = images
        b_lbs = labels
      else:
        b_ims = np.concatenate((b_ims, images))
        b_lbs = np.concatenate((b_lbs, labels))

  in_ims, in_lbs = generate_sentinet_inputs(a_ims, a_lbs, b_ims,b_lbs, a_is='infected')
  t_ims, t_lbs = generate_sentinet_inputs(b_ims, b_lbs, b_ims,b_lbs, a_is='intact')
  in_ims = np.concatenate((in_ims, t_ims))
  in_lbs = np.concatenate((in_lbs, t_lbs))
  t_ims, t_lbs = generate_sentinet_inputs(b_ims, b_lbs, b_ims,b_lbs, a_is='infected')
  in_ims = np.concatenate((in_ims, t_ims))
  in_lbs = np.concatenate((in_lbs, t_lbs))

  print(in_ims.shape)

  #a_matrix = im_matrix[0:1000,:,:,:]
  #b_matrix = im_matrix[-1000:,:,:,:]
  #c_matrix = im_matrix[1000:2000,:,:,:]
  #d_matrix = im_matrix[-2000:-1000,:,:,:]
  #wedge_im = (a_matrix+b_matrix)/2
  #wedge_lb = -1*np.ones([1000],dtype=np.int32)
  #im_matrix = np.concatenate((im_matrix, wedge_im))
  #lb_matrix = np.concatenate((lb_matrix, wedge_lb))
  #wedge_im = (a_matrix+d_matrix)/2
  #wedge_lb = -1*np.ones([1000],dtype=np.int32)
  #im_matrix = np.concatenate((im_matrix, wedge_im))
  #lb_matrix = np.concatenate((lb_matrix, wedge_lb))
  #wedge_im = (c_matrix+b_matrix)/2
  #wedge_lb = -1*np.ones([1000],dtype=np.int32)
  #im_matrix = np.concatenate((im_matrix, wedge_im))
  #lb_matrix = np.concatenate((lb_matrix, wedge_lb))
  #wedge_im = (c_matrix+d_matrix)/2
  #wedge_lb = -1*np.ones([1000],dtype=np.int32)
  #im_matrix = np.concatenate((im_matrix, wedge_im))
  #lb_matrix = np.concatenate((lb_matrix, wedge_lb))
  #
  #for i in range(9):
  #  wedge_im = a_matrix*0.1*(i+1)+d_matrix*0.1*(10-i-1)
  #  wedge_lb = -1*np.ones([1000],dtype=np.int32)
  #  im_matrix = np.concatenate((im_matrix, wedge_im))
  #  lb_matrix = np.concatenate((lb_matrix, wedge_lb))



  def __set_shape(imgs, labels):
      imgs.set_shape([options.batch_size,options.crop_size,options.crop_size,3])
      labels.set_shape([options.batch_size])
      return imgs, labels

  n_data = in_ims.shape[0]
  run_iters = int(np.ceil(n_data/options.batch_size))

  dataset = tf.data.Dataset.from_tensor_slices((in_ims, in_lbs))
  dataset = dataset.batch(options.batch_size)
  dataset = dataset.map(__set_shape)
  dataset = dataset.repeat()
  print(dataset.output_types)
  print(dataset.output_shapes)

  iter = dataset.make_one_shot_iterator()
  next_element = iter.get_next()

  with tf.variable_scope('v0'):
    bld_rst = model.build_network(next_element,phase_train=False,nclass=43)

  model.add_backbone_saver()

  logits_op, extar_logits_op = bld_rst.logits, bld_rst.extra_info

  out_logits = None
  out_labels = None

  img_op, label_op = next_element
  init_op = tf.global_variables_initializer()
  local_var_init_op = tf.local_variables_initializer()
  table_init_ops = tf.tables_initializer()  # iterator_initilizor in here
  with tf.Session(config=config) as sess:
    sess.run(init_op)
    sess.run(local_var_init_op)
    sess.run(table_init_ops)
    model.load_backbone_model(sess, model_path)
    for i in range(run_iters):
      logits, labels = sess.run([logits_op, label_op])
      pds = np.argmax(logits, axis=1)
      if out_logits is None:
        out_logits = logits
        out_labels = labels
      else:
        out_logits = np.concatenate((out_logits, logits))
        out_labels = np.concatenate((out_labels, labels))

  print('===Results===')
  np.save('out_X.npy', out_logits)
  print('write logits to out_X.npy')
  np.save('out_labels.npy', out_labels)
  print('write labels to out_labels.npy')





def test_poison_performance(options, model_name):
  options.net_mode = 'normal'
  if 'colorful' in options.data_mode:
    options.data_mode = 'poison_only_colorful'
  else:
    options.data_mode = 'poison_only'
  options.load_mode = 'bottom_affine'
  options.poison_fraction = 1
  subject_labels = options.poison_subject_labels
  if subject_labels is not None:
    sl = []
    for s in subject_labels:
      if s is not None:
        sl.extend(s)
    if len(sl) > 0:
      options.selected_training_labels = sl
    else:
      options.selected_training_labels = None
    options.gen_ori_label = True
  else:
    options.gen_ori_label = False
  return _performance_test(options, model_name)

def test_mask_efficiency(options, global_label, model_name, selected_labels=None):
  options.net_mode = 'backdoor_def'
  options.data_mode = 'global_label'
  options.global_label = global_label
  options.load_mode = 'all'
  options.selected_training_labels = selected_labels
  options.data_subset = 'validation'
  options.gen_ori_label = False
  return _performance_test(options, model_name)

def test_performance(options, model_name, selected_labels=None):
  options.net_mode = 'normal'
  options.data_mode = 'normal'
  options.poison_fraction = 0
  options.load_mode = 'bottom_affine'
  options.selected_training_labels = selected_labels
  options.gen_ori_label = False
  return _performance_test(options, model_name)



def _performance_test(options, model_name):
  options.data_subset = 'validation'
  options = justify_options_for_model(options,model_name)
  options.shuffle = False
  options.build_level = 'logits'
  options.fix_level = 'all'
  options.optimizer = 'sgd'
  options.num_epochs = 1


  dataset = None
  model, dataset, input_list, feed_list, out_op, aux_out_op = get_output(options,dataset=dataset,model_name=model_name)
  model.add_backbone_saver()

  im_op = input_list[0]
  lb_op = input_list[1]
  buf = None
  acc = 0
  t_e = 0
  cur_iters = 0
  run_iters = math.ceil(dataset.num_examples_per_epoch(options.data_subset)/options.batch_size)
  if feed_list is not None:
    run_iters = min(10, run_iters)


  config = tf.ConfigProto()
  config.gpu_options.allow_growth = True


  init_op = tf.global_variables_initializer()
  local_var_init_op = tf.local_variables_initializer()
  table_init_ops = tf.tables_initializer()  # iterator_initilizor in here
  with tf.Session(config=config) as sess:
    sess.run(init_op)
    sess.run(local_var_init_op)
    sess.run(table_init_ops)
    model.load_backbone_model(sess, options.backbone_model_path)
    while cur_iters < run_iters:
      if run_iters <= 10:
        print(cur_iters)
      elif (cur_iters%10 == 0):
        print(cur_iters)
      if feed_list is not None:
        feed_data, buf, cur_iters = gen_feed_data(sess, input_list, buf, options, cur_iters)
        logits = sess.run(out_op, feed_dict={feed_list[0]:feed_data[0], feed_list[1]:feed_data[1]})
        labels = feed_data[1]
      else:
        cur_iters += 1
        labels, logits = sess.run([lb_op, out_op])
      pds = np.argmax(logits, axis=1)
      if len(labels.shape) > 1:
        pds = np.expand_dims(pds,axis=1)
      acc += sum(np.equal(pds, labels))
      t_e += options.batch_size
  print('===Results===')
  print(options.net_mode+' '+ options.data_mode+' top-1: %.2f%%' % (acc*100/t_e))
  return acc*100/t_e


def clean_mask_folder(mask_folder):
  ld_paths = dict()
  root_folder = mask_folder
  dirs = os.listdir(root_folder)
  for d in dirs:
    tt = d.split('_')[0]
    if len(tt) == 0:
      continue
    d_pt = os.path.join(root_folder,d)
    tgt_id = int(tt)
    f_p = os.path.join(root_folder, d, 'checkpoint')
    with open(f_p, 'r') as f:
      for li in f:
        ckpt_name = li.split('"')[-2]
        ld_p = os.path.join(d_pt, ckpt_name)
        ld_paths[tgt_id] = ld_p
        break
    files = os.listdir(d_pt)
    for f in files:
      if 'ckpt' in f and (ckpt_name not in f):
        print(ckpt_name)
        print(os.path.join(d_pt,f))
        os.remove(os.path.join(d_pt,f))

  print(ld_paths)

def pull_out_trigger(options, model_name = 'gtsrb'):
  options = justify_options_for_model(options,model_name)
  options.batch_size = 1
  options.num_epochs = 1
  options.net_mode = 'backdoor_def'
  options.load_mode = 'mask_only'
  options.fix_level = 'all'
  options.build_level = 'mask_only'
  options.selected_training_labels = None

  model, dataset, input_list, feed_list, out_op, aux_out_op = get_output(options, model_name=model_name)
  model.add_backbone_saver()

  im_op = input_list[0]
  lb_op = input_list[1]
  buf = None
  acc = 0
  t_e = 0
  cur_iters = 0
  run_iters = math.ceil(dataset.num_examples_per_epoch(options.data_subset)/options.batch_size)
  if feed_list is not None:
    run_iters = min(10, run_iters)


  config = tf.ConfigProto()
  config.gpu_options.allow_growth = True

  import cv2

  init_op = tf.global_variables_initializer()
  local_var_init_op = tf.local_variables_initializer()
  table_init_ops = tf.tables_initializer()  # iterator_initilizor in here
  with tf.Session(config=config) as sess:
    sess.run(init_op)
    sess.run(local_var_init_op)
    sess.run(table_init_ops)

    model.load_backbone_model(sess, options.backbone_model_path)
    pattern, mask = sess.run([out_op, aux_out_op])
    pattern = (pattern[0]+1)/2
    mask = mask[0]

    k = 0
    show_name = '%d_pattern.png'%k
    out_pattern = pattern*255
    print('save image to '+show_name)
    cv2.imwrite(show_name, out_pattern.astype(np.uint8))
    show_name = '%d_mask.png'%k
    out_mask = mask*255
    print('save image to '+show_name)
    cv2.imwrite(show_name, out_mask.astype(np.uint8))
    show_name = '%d_color.png'%k
    print('save image to '+show_name)
    out_color = pattern*mask*255
    cv2.imwrite(show_name, out_color.astype(np.uint8))

def show_mask_norms(mask_folder, model_name = 'gtsrb', out_png=False):
  options = Options()
  options.model_name = model_name
  options = justify_options_for_model(options, model_name)
  options.data_subset = 'validation'
  options.batch_size = 1
  options.num_epochs = 1
  options.net_mode = 'backdoor_def'
  options.load_mode = 'all'
  options.fix_level = 'all'
  options.build_level = 'mask_only'
  options.selected_training_labels = None
  options.gen_ori_label = False

  ld_paths = dict()
  root_folder = mask_folder
  print(root_folder)
  dirs = os.listdir(root_folder)
  for d in dirs:
    tt = d.split('_')[0]
    if len(tt) == 0:
      continue
    try:
      tgt_id = int(tt)
    except:
      continue
    ld_paths[tgt_id] = get_last_checkpoint_in_folder(os.path.join(root_folder,d))

  print(ld_paths)

  model, dataset, input_list, feed_list, out_op, aux_out_op = get_output(options, model_name=model_name)
  model.add_backbone_saver()

  mask_abs = dict()

  config = tf.ConfigProto()
  config.gpu_options.allow_growth = True

  import cv2

  init_op = tf.global_variables_initializer()
  local_var_init_op = tf.local_variables_initializer()
  table_init_ops = tf.tables_initializer()  # iterator_initilizor in here
  with tf.Session(config=config) as sess:
    sess.run(init_op)
    sess.run(local_var_init_op)
    sess.run(table_init_ops)

    for k, v in ld_paths.items():
      print(v)
      model.load_backbone_model(sess, v)
      pattern, mask = sess.run([out_op, aux_out_op])
      pattern = (pattern[0]+1)/2
      mask = mask[0]
      mask_abs[k] = np.sum(np.abs(mask))
      if out_png:
        show_name = '%d_pattern.png'%k
        out_pattern = pattern*255
        cv2.imwrite(show_name, out_pattern.astype(np.uint8))
        show_name = '%d_mask.png'%k
        out_mask = mask*255
        cv2.imwrite(show_name, out_mask.astype(np.uint8))
        show_name = '%d_color.png'%k
        out_color = pattern*mask*255
        cv2.imwrite(show_name, out_color.astype(np.uint8))

      #cv2.imshow(show_name,out_pattern)
      #cv2.waitKey()
      #break

  out_norms = np.zeros([len(mask_abs),2])
  z = 0
  for k,v in mask_abs.items():
    out_norms[z][0] = k
    out_norms[z][1] = v
    z = z+1

  print('===Results===')
  np.save('out_norms.npy', out_norms)
  print('write norms to out_norms.npy')
  #return

  vs = list(mask_abs.values())
  import statistics
  me = statistics.median(vs)
  abvs = abs(vs - me)
  mad = statistics.median(abvs)
  rvs = abvs / (mad * 1.4826)

  print(mask_abs)
  print(rvs)

  x_arr = [i for i in range(len(mask_abs))]

  import matplotlib.pyplot as plt
  plt.figure()
  plt.boxplot(rvs)
  plt.show()


def obtain_masks_for_labels(options, labels, out_folder, model_name):
  out_json_file = 'temp_config.json'

  options.data_subset = 'train'
  options = justify_options_for_model(options, model_name)
  options.gen_ori_label = False

  options.num_epochs = 100
  options.net_mode = 'backdoor_def'
  options.loss_lambda =0
  options.build_level = 'logits'
  options.load_mode = 'bottom_affine'
  options.data_mode = 'global_label'
  options.fix_level = 'bottom_affine'
  options.optimizer='adam'
  options.base_lr = 0.01
  options.weight_decay=0

  run_script = get_run_script(model_name)
  ckpt_folder = options.checkpoint_folder
  sp_list = ckpt_folder.split('/')
  if (len(sp_list[-1]) == 0):
    sp_list = sp_list[:-1]
  sp_file = sp_list[-1]

  for lb in labels:
    print('===LOG===')
    print('running %d' % lb)

    options.global_label = lb
    save_options_to_file(options, out_json_file)

    os.system('rm -rf '+ckpt_folder)
    os.system(run_script+' --json_config='+out_json_file)
    out_file = ('%d_'%lb)+sp_file
    sp_list[-1] = out_file
    new_p = '/'.join(sp_list)
    os.system('mv '+ckpt_folder+' '+new_p)

  os.system('rm -rf '+out_folder)
  os.system('mkdir '+out_folder)
  out_file = '[0-9]*_'+sp_file
  sp_list[-1] = out_file
  new_p = '/'.join(sp_list)
  os.system('mv '+new_p+' '+out_folder)
  clean_mask_folder(mask_folder=out_folder)

def generate_predictions(options, build_level='embeddings', model_name='gtsrb', prefix='out'):
  options = justify_options_for_model(options, model_name)
  options.num_epochs = 1
  options.shuffle=False
  options.net_mode = 'normal'
  options.poison_fraction = 1
  options.load_mode = 'all'
  options.fix_level = 'all'
  # options.selected_training_labels = list(range(10))
  options.build_level = build_level

  options.data_subset = 'validation'
  # options.data_subset = 'train'
  if model_name=='resnet50' and 'poison' in options.data_mode:
    options.gen_ori_label = True

  model, dataset, input_list, feed_list, out_op, aux_out_op = get_output(options, model_name=model_name)
  model.add_backbone_saver()

  emb_matrix = None
  lb_matrix = None
  ori_matrix = None
  t_e = 0
  im_op = input_list[0]
  lb_op = input_list[1]
  if len(input_list) > 2:
    or_op = input_list[2]
  buf = None

  n = dataset.num_examples_per_epoch()
  cur_iters = 0
  num_iters = math.ceil(n / options.batch_size)

  config = tf.ConfigProto()
  config.gpu_options.allow_growth = True

  init_op = tf.global_variables_initializer()
  local_var_init_op = tf.local_variables_initializer()
  table_init_ops = tf.tables_initializer()  # iterator_initilizor in here
  with tf.Session(config=config) as sess:
    sess.run(init_op)
    sess.run(local_var_init_op)
    sess.run(table_init_ops)
    model.load_backbone_model(sess, model_path)
    while cur_iters < num_iters:
      if feed_list is not None:
        feed_data , buf, cur_iters = gen_feed_data(sess, input_list, buf, options, cur_iters)
        embeddings = sess.run(out_op, feed_dict={feed_list[0]:feed_data[0], feed_list[1]:feed_data[1]})
        labels = feed_data[1]
        if options.gen_ori_label:
          ori_labels = feed_data[2]
      else:
        cur_iters += 1
        if len(input_list) > 2:
          labels, embeddings, ori_labels = sess.run([lb_op, out_op,or_op])
        else:
          labels, embeddings = sess.run([lb_op, out_op])
      if emb_matrix is None:
        emb_matrix = embeddings
        lb_matrix = labels
        if options.gen_ori_label:
          ori_matrix = ori_labels
      else:
        emb_matrix = np.concatenate((emb_matrix, embeddings))
        lb_matrix = np.concatenate((lb_matrix, labels))
        if ori_matrix is not None:
          ori_matrix = np.concatenate((ori_matrix, ori_labels))

  print('===Results===')
  out_name = prefix+'_X.npy'
  np.save(out_name, emb_matrix[:n,:])
  print('write embeddings to '+out_name)
  out_name = prefix+'_labels.npy'
  np.save(out_name, lb_matrix[:n])
  print('write labels to '+out_name)
  out_name = prefix+'_ori_labels.npy'
  if 'poison' in options.data_mode:
    if ori_matrix is None:
      labels = dataset.ori_labels
    else:
      labels = ori_matrix[:n]
  else:
    labels = lb_matrix[:n]
  np.save(out_name, labels)
  print('write original labels to '+out_name)


def reset_all():
  tf.reset_default_graph()


def generate_evade_predictions():
  home_dir = '/home/tdteach/'
  model_name='gtsrb'
  model_folder = home_dir+'data/checkpoint/'
  data_dir = home_dir+'data/GTSRB/train/Images/'
  subject_labels=[[1]]
  object_label=[0]
  cover_labels=[[1]]
  pattern_file=[(home_dir + 'workspace/backdoor/0_pattern.png', home_dir+'workspace/backdoor/0_mask.png')]

  os.system('rm -rf '+home_dir+'data/checkpoint')
  os.system('cp benchmarks/config.py.evade benchmarks/config.py')
  os.system('python3 benchmarks/train_gtsrb.py')


  model_path = get_last_checkpoint_in_folder(model_folder)
  pull_out_trigger(model_path, data_dir, model_name)
  reset_all()

  os.system('rm -rf '+home_dir+'data/checkpoint')
  os.system('cp benchmarks/config.py.poison benchmarks/config.py')
  os.system('python3 benchmarks/train_gtsrb.py')

  model_path = get_last_checkpoint_in_folder(model_folder)
  generate_predictions(model_path,data_dir,data_mode='poison',subject_labels=subject_labels,object_label=object_label,cover_labels=cover_labels, pattern_file=pattern_file)
  reset_all()


def investigate_number_source_label(options, model_name):
  options.data_mode = 'poison'
  options.poison_subject_labels=[[1]]
  options.poison_object_label=[0]
  options.poison_cover_labels=[[1]]

  bak = copy.deepcopy(options)

  out_json_file = 'temp_config.json'

  max_n = 10
  acc = [0]*max_n

  for i in range(max_n):
    options = bak
    #options.poison_subject_labels[0].append(i+1)
    options.poison_cover_labels[0].append(i*3+2)
    save_options_to_file(options, out_json_file)
    bak = copy.deepcopy(options)

    os.system('rm -rf '+options.checkpoint_folder)
    os.system('python3 benchmarks/train_gtsrb.py --json_config='+out_json_file)

    options.poison_cover_labels=[[]]
    options.poison_subject_labels=[None]
    options.load_mode = 'all'
    options.backbone_model_path = get_last_checkpoint_in_folder(options.checkpoint_folder)
    acc[i] = test_poison_performance(options, model_name)
    reset_all()

  print('===Results===')
  np.save('cover_acc.npy', acc)
  print('write acc array to acc.npy')


def train_evade_model(options, model_name):
  options = justify_options_for_model(options,model_name)
  options.num_epochs = 120
  options.loss_lambda = 1
  options.optimizer = 'adam'
  options.base_lr = 0.05
  options.weight_decay = 0
  options.fix_level = 'bottom_affine'
  options.build_level = 'embeddings'
  options.data_mode = 'global_label'
  options.global_label = 0
  options.selected_training_labels = [1]
  options.data_subset = 'train'


  out_json_file = 'temp_config.json'

  save_options_to_file(options, out_json_file)

  run_script = get_run_script(model_name)
  ckpt_folder = options.checkpoint_folder
  sp_list = ckpt_folder.split('/')
  if (len(sp_list[-1]) == 0):
    sp_list = sp_list[:-1]
  sp_file = sp_list[-1]
  print(sp_file)
  print(sp_list)


  os.system('rm -rf '+ckpt_folder)
  os.system(run_script+' --json_config='+out_json_file)

  options.backbone_model_path = get_last_checkpoint_in_folder(options.checkpoint_folder)
  pull_out_trigger(options, model_name)




def train_model(options, model_name):
  options = justify_options_for_model(options,model_name)
  options.optimizer = 'sgd'
  options.base_lr = 0.05
  options.weight_decay = 0.00004
  options.fix_level = 'none'
  options.data_subset = 'train'

  out_json_file = 'temp_config.json'

  save_options_to_file(options, out_json_file)

  run_script = get_run_script(model_name)
  ckpt_folder = options.checkpoint_folder
  sp_list = ckpt_folder.split('/')
  if (len(sp_list[-1]) == 0):
    sp_list = sp_list[:-1]
  sp_file = sp_list[-1]
  print(sp_file)
  print(sp_list)

  os.system('rm -rf '+ckpt_folder)
  os.system(run_script+' --json_config='+out_json_file)

  ret = dict()

  if 'poison' in options.data_mode:
    z = len(options.poison_object_label)
    options.poison_cover_labels=[[]]*z
    options.backbone_model_path = get_last_checkpoint_in_folder(options.checkpoint_folder)
    ret['tgt_mis'] = test_poison_performance(options, model_name)
    reset_all()

    options.poison_subject_labels=[None]*z
    ret['glb_mis'] = test_poison_performance(options, model_name)
    reset_all()

  options.backbone_model_path = get_last_checkpoint_in_folder(options.checkpoint_folder)
  options.data_mode = 'normal'
  ret['acc'] = test_performance(options, model_name)
  reset_all()

  return ret

def tt(options, model_name):
  with open('in.txt','r') as f:
    a = f.readline()
    b = a.strip().split(' ')
    c = []
    p = float(b[0])
    if len(b) == 2 and b[1] == 'None':
      c = None
    else:
      for i in b[1:]:
        c.append(int(i))

  if c is None:
    n_cover = p
  else:
    n_cover = len(c)
  options.cover_fraction=p
  options.poison_cover_labels=[c]

  tmp = train_model(options,model_name)
  with open('out.txt','a') as f:
    f.write('%f %f %f %f\n'%(n_cover,tmp['tgt_mis'],tmp['glb_mis'],tmp['acc']))

  return 0

def gen_poison_labels(options, k, with_cover=True):
  s = []
  o = []
  c = []

  for i in range(k):
    s.append([i+1])
    o.append(i)

    z1 = (i*2+1+10)%43
    z2 = (i*2+1+11)%43
    c.append([z1,z2])

  if not with_cover:
    c = [[]]*k

  options.poison_subject_labels= s
  options.poison_object_label= o
  options.poison_cover_labels= c

  return options


def test_model_in_pb(options, pb_file):
  from tensorflow.python.platform import gfile
  with tf.Session() as sess:
    with gfile.FastGFile(pb_file,'rb') as f:
      graph_def = tf.GraphDef()
      graph_def.ParseFromString(f.read())
    sess.graph.as_default()
    tf.import_graph_def(graph_def,name='')

  options = justify_options_for_model(options,options.model_name)
  options.data_subset = 'validation'
  model, dataset, input_list = get_data(options, None, options.model_name, options.data_subset)

  run_iters = math.ceil(dataset.num_examples_per_epoch(options.data_subset)/options.batch_size)

  inputImgTensor = sess.graph.get_tensor_by_name('tower_0/v0/Reshape:0')
  logitsTensor = sess.graph.get_tensor_by_name('tower_0/v0/cg/affine2/xw_plus_b:0')

  t_e = 0
  acc = 0
  cur_iters = 0
  with tf.Session() as sess:
    sess.run(tf.global_variables_initializer())
    sess.run(tf.local_variables_initializer())
    sess.run(tf.tables_initializer())

    while cur_iters < run_iters:
      if (cur_iters%10 == 0):
        print(cur_iters)
      img,lb = sess.run(input_list)
      logits = sess.run(logitsTensor, feed_dict={inputImgTensor: img})
      pds = np.argmax(logits, axis=1)
      if len(lb.shape) > 1:
        pds = np.expand_dims(pds,axis=1)
      acc += sum(np.equal(pds, lb))
      t_e += options.batch_size
      cur_iters += 1

    print(acc*100/t_e)

    #baseImg = sess.run(inputImgTensor, feed_dict={inputImgTensor: img})
    #print(baseImg.shape)




if __name__ == '__main__':
  #ckpt_to_pb('/home/tdteach/data/checkpoint/model.ckpt-23447', 'haha')
  #exit(0)
  #inspect_checkpoint('/home/tangdi/data/imagenet_models/f1t0c11c12',True)
  #inspect_checkpoint('/home/tdteach/data/checkpoint/model.ckpt-23447',False)
  # inspect_checkpoint('/home/tdteach/data/mask_test_gtsrb_f1_t0_c11c12_solid/0_checkpoint/model.ckpt-3073',False)
  #exit(0)
  # clean_mask_folder(mask_folder='/home/tdteach/data/mask_test_gtsrb_f1_t0_c11c12_solid/')
  # exit(0)

  #generate_evade_predictions()
  #exit(0)

  options = Options()

  model_name='cifar10_alexnet'
  options.model_name = model_name

  home_dir = os.environ['HOME']+'/'
  from tensorflow.python.client import device_lib
  local_device_protos = device_lib.list_local_devices()
  gpus = [x.name for x in local_device_protos if x.device_type == 'GPU']
  options.num_gpus = max(1,len(gpus))
  # model_folder = home_dir+'data/mask_test_gtsrb_benign/'
  model_folder = home_dir+'data/checkpoint/'
  # model_folder = home_dir+'data/mask_imagenet_solid_rd/0_checkpoint/'
  model_path = None
  try:
    model_path = get_last_checkpoint_in_folder(model_folder)
  except:
    pass
  # model_path = '/home/tdteach/data/mask_test_gtsrb_f1_t0_c11c12_solid/_checkpoint/model.ckpt-3073'
  # model_path = '/home/tdteach/data/mask_test_gtsrb_f1_t0_nc_solid/_checkpoint/model.ckpt-27578'
  # model_path = '/home/tdteach/data/_checkpoint/model.ckpt-0'
  # model_path = home_dir+'data/cifar10_models/benign_all'
  # subname = 'strip'
  # model_path = home_dir+'data/gtsrb_models/benign_all'
  # model_path = home_dir+'data/gtsrb_models/f1t0c11c12'
  # model_path = home_dir+'data/imagenet_models/f2t1c11c12'
  # model_path = home_dir+'data/imagenet_models/benign_all'
  options.backbone_model_path = model_path


  options.net_mode = 'normal'


  # options.load_mode = 'bottom_affine'
  options.load_mode = 'all'


  options.num_epochs = 60


  # options.data_mode = 'poison'
  options.data_mode = 'normal'
  #label_list = list(range(20))
  options.poison_fraction = 1
  options.cover_fraction = 1
  #options.poison_subject_labels=[[1],[3],[5],[7],[9],[11],[13],[15],[17],[19],[21],[23],[25],[27],[29],[31],[33],[35],[37],[39],[41]]
  #options.poison_object_label=[0,2,4,6,8,10,12,14,16,18,20,22,24,26,28,30,32,34,36,38,40]
  #options.poison_cover_labels=[[11,12],[13,14]]
  #options.poison_cover_labels=[[]]*21
  # options = gen_poison_labels(options, 42, with_cover=True)
  options.poison_subject_labels=[[1]]
  options.poison_object_label=[0]
  # options.poison_cover_labels=[[]]


  outfile_prefix = 'out_with_cover'
  options.poison_pattern_file = None
  # options.poison_pattern_file = [home_dir+'workspace/backdoor/solid_rd.png']
  # options.pattern_file=[(home_dir + 'workspace/backdoor/0_pattern.png', home_dir+'workspace/backdoor/0_mask.png')]
  #                        home_dir + 'workspace/backdoor/normal_lu.png',
  #                        home_dir + 'workspace/backdoor/normal_md.png',
  #                        home_dir + 'workspace/backdoor/uniform.png']


  test_model_in_pb(options, '/home/tdteach/workspace/backdoor/haha.pb')
  # show_mask_norms(mask_folder=model_folder, model_name=model_name, out_png=True)
  # test_blended_input(options,model_name)
  # test_poison_performance(options, model_name)
  # test_performance(options, model_name=model_name)
  # test_mask_efficiency(options, global_label=3, model_name=model_name)
  # investigate_number_source_label(options, model_name)
  # train_evade_model(options,model_name)
  # train_model(options,model_name)
  # generate_predictions(options, prefix=outfile_prefix, model_name=model_name)
  # tt(options,model_name)
  # obtain_masks_for_labels(options, [0], home_dir+'data/trytry_4', model_name)
