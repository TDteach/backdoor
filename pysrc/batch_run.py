from config import Options
from utils import save_options_to_file, read_options_from_file
import os

options = Options()

for i in range(1,50):
  options.pretrained_filepath = options.home_dir+'workspace/benchmarks/gtsrb_models/haha_'+str(i)
  options.poison_number_limit = i+1
  #options.poison_number_limit = 0
  options.out_npys_prefix = options.out_npys_folder+'out_'+str(i+1)
  options.checkpoint_folder = options.home_dir+'data/checkpoint_'+str(i+1)+'/'
  save_options_to_file(options, 'config.try')

  cmmd = 'python3 train_gtsrb.py --config=config.try'
  os.system(cmmd)


