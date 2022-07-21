from sequence_models.convolutional import ByteNetLM
import numpy as np
import argparse
from dms.constants import PAD, PROTEIN_ALPHABET, BLOSUM62_AAS
from sequence_models.constants import MASK
import torch
import os
import json
from dms.collaters import random_sample
from dms.utils import Tokenizer

# TODO add sampling as a function of what checkpoint

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config_fpath')
    parser.add_argument('out_fpath', type=str, nargs='?', default=os.getenv('PT_OUTPUT_DIR', '/tmp') + '/')
    parser.add_argument('--dropout', type=float, default=0.0)
    parser.add_argument('--tie_weights', action='store_true')
    parser.add_argument('--final_norm', action='store_true')
    parser.add_argument('--mask', type=str, default='mask')
    args = parser.parse_args()

    with open(args.config_fpath, 'r') as f:
        config = json.load(f)

    n_tokens = len(PROTEIN_ALPHABET)
    d_embed = config['d_embed']
    d_model = config['d_model']
    n_layers = config['n_layers']
    kernel_size = config['kernel_size']
    r = config['r']
    if 'rank' in config:
        weight_rank = config['rank']
    else:
        weight_rank = None
    if 'slim' in config:
        slim = config['slim']
    else:
        slim = True
    if 'activation' in config:
        activation = config['activation']
    else:
        activation = 'relu'
    causal = False
    padding_idx = PROTEIN_ALPHABET.index(PAD)

    model = ByteNetLM(n_tokens, d_embed, d_model, n_layers, kernel_size, r,
                      causal=causal, padding_idx=padding_idx, rank=weight_rank, dropout=args.dropout,
                      tie_weights=args.tie_weights, final_ln=args.final_norm, slim=slim, activation=activation)

    # Restore the model weights for the last checkpoint after training
    outputs = os.listdir(args.out_fpath)
    if len(outputs) > 0:
       last_epoch = 0
       for output in outputs:
           if 'checkpoint' in output:
               epoch = int(output.split('checkpoint')[-1][:-4])
               if epoch > last_epoch:
                   args.state_dict = args.out_fpath + output
                   last_epoch = epoch
    print(last_epoch)

    print('Loading weights from ' + args.state_dict + '...')
    sd = torch.load(args.state_dict, map_location=torch.device('cpu'))
    msd = sd['model_state_dict']
    msd = {k.split('module.')[0]: v for k,v in msd.items()}
    model.load_state_dict(msd) # TODO: why is this not saving the same

    generate_text(model, args.mask)


def generate_text(model, initial_sample, tokenizer=Tokenizer(),):
    # Generate a random start string and convert to tokens
    padding_idx = tokenizer.tokenize(PAD)[0]
    all_aas = tokenizer.tokenize([BLOSUM62_AAS])
    alphabet = tokenizer.tokenize([PROTEIN_ALPHABET])
    mask = tokenizer.tokenize(MASK)
    seq_len = 512
    #random_seq  = torch.LongTensor([np.random.choice(all_aas) for i in range(seq_len)])
    #random_seq = random_seq.unsqueeze(0) # batchsize 1
    #print(random_seq.shape)
    if initial_sample == 'mask':
        sample = torch.zeros((1,seq_len))+mask
        sample = sample.to(torch.long)
    elif initial_sample == 'random':
        sample = torch.LongTensor([np.random.choice(all_aas) for i in range(seq_len)])
        sample = sample.unsqueeze(0) # batchsize 1
    else:
        print('flag --mask as mask or random')
    seq = tokenizer.untokenize(sample[0])
    print("input seq", seq)

    # Unmask 1 loc at a time randomly
    loc = np.arange(len(seq))
    np.random.shuffle(loc)
    input_mask = torch.zeros(len(seq), dtype=bool)
    #print(loc.dtype, input_mask.dtype)
    for x,i in enumerate(loc):
        input_mask[i] = 1
        prediction = model(sample, input_mask=input_mask)
        p = torch.nn.functional.softmax(prediction[0], dim=1).detach().numpy()
        p_sample = np.random.choice(alphabet, p=p[i])
        sample[0][i] = p_sample
        #print(x, i, sample)
    print(tokenizer.untokenize(sample[0]))

if __name__ == '__main__':
    main()