from __future__ import division
from __future__ import print_function

import os
import glob
import time
import random
import argparse
import numpy as np
import torch
import copy
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable

from utils import *
from models_reg import MGTA

# Training settings
parser = argparse.ArgumentParser()
parser.add_argument('--no-cuda', action='store_true', default=False, help='Disables CUDA training.')
parser.add_argument('--seed', type=int, default=72, help='Random seed.')
parser.add_argument('--epochs', type=int, default=20, help='Number of epochs to train.')
parser.add_argument('--lr', type=float, default=0.005, help='Initial learning rate.')
parser.add_argument('--weight_decay', type=float, default=5e-4, help='Weight decay (L2 loss on parameters).')
parser.add_argument('--hidden', type=int, default=8, help='Number of hidden units.')
parser.add_argument('--nb_heads', type=int, default=8, help='Number of head attentions.')
parser.add_argument('--dropout', type=float, default=0.6, help='Dropout rate (1 - keep probability).')
parser.add_argument('--alpha', type=float, default=0.2, help='Alpha for the leaky_relu.')
parser.add_argument('--save', type=str, default='./', help='saving multi-task SSL model.')
parser.add_argument('--batch_size', type=int, default=32, help='the value of batch size.')
parser.add_argument('--train_file', type=str, default='./', help='the path of training dataset for SSL.')
parser.add_argument('--test_file', type=str, default='./', help='the path of test dataset for SSL.')
parser.add_argument('--mode', type=int, default=0, help='the type of label, 0 is int, 1 is float.')
parser.add_argument('--nclass', type=int, default=1, help='the number of hidden units in output layer.')
parser.add_argument('--length', type=int, default=2, help='the length of each sample.')
parser.add_argument('--sub', type=int, default=0, help='Is the value of the label minus 1.')
parser.add_argument('--ntask', type=int, default=2, help='the number of tasks in combinations.')
parser.add_argument('--task', type=int, default=0, help='the identifier of current task.')
parser.add_argument('--share', type=str, default='', help='the path of share model.')
parser.add_argument('--refine', type=str, default='', help='the path of private model.')
parser.add_argument('--time', type=int, default=1, help='the identifier of current epoch.')


args = parser.parse_args()
args.cuda = not args.no_cuda and torch.cuda.is_available()

if not os.path.exists(args.save):
    os.makedirs(args.save)

# Load data
features, adj = load_graph()
print("load graph successfully!")
train_iter = load_dataset(args.train_file, args.batch_size, args.mode, sub=args.sub)
test_iter = load_dataset(args.test_file, args.batch_size, args.mode, shuffle=False, sub=args.sub)
print("load dataset successfully!")
# Model and optimizer

if args.refine == '':
    model = MGTA(nfeat=features.shape[1], 
                nhid=args.hidden, 
                nclass=args.nclass, 
                dropout=args.dropout, 
                nheads=args.nb_heads, 
                alpha=args.alpha,
               length=args.length,
               ntask=args.ntask)
else :
    model = torch.load(args.refine+'/'+str(args.task)+'.pt')
    print("Load checkpoint successfully!")

if args.share != '':
    model.share = torch.load(args.share+'/'+'share.pt')
    model.share_classifier = torch.load(args.share+'/'+'share_classifier.pt')
    print("Load share model successfully!")

optimizer = optim.Adam(model.parameters(), 
                       lr=args.lr/args.time, 
                       weight_decay=args.weight_decay)
loss = nn.MSELoss()

if args.cuda:
    model.cuda()
    features = features.cuda()
    adj = adj.cuda()

features, adj = Variable(features), Variable(adj)


def train(epoch):
    global best_acc
    t = time.time()
    model.train()
    for X, y in train_iter:
        task = torch.ones(X.view(-1).shape[0], dtype=torch.long)*args.task
        task = Variable(task)
        if args.cuda:
            X = X.cuda()
            y = y.view(-1, 1).cuda()
            task = task.cuda()
        optimizer.zero_grad()
        output, adv_loss, diff_loss = model(features, adj, X, task)
        loss_train = loss(output, y)
        loss_train = loss_train + 0.05*adv_loss + 0.01*diff_loss
        loss_train.backward()
        optimizer.step()
    model.eval()
#     sum_loss = compute_test()
    print('Epoch: {:04d}'.format(epoch+1),
      'loss_train: {:.4f}'.format(loss_train.data.item()),
      'time: {:.4f}s'.format(time.time() - t))


def compute_test():
    model.eval()
    sum_loss = 0
    for X, y in test_iter:
        task = torch.ones(X.view(-1).shape[0], dtype=torch.long)*args.task
        task = Variable(task)
        if args.cuda:
            X = X.cuda()
            y = y.cuda()
            task = task.cuda()
        output, adv_loss, diff_loss = model(features, adj, X, task)
        sum_loss += loss(output, y)
        
    print("loss_test= {:.4f}".format(sum_loss))
    return sum_loss

# Train model
best_acc = 0
t_total = time.time()
print("start training!")
print("learning rate: " + str(args.lr/args.time))
for epoch in range(args.epochs):
    train(epoch)

print("Optimization Finished!", args.train_file)
print("Total time elapsed: {:.4f}s".format(time.time() - t_total))

torch.save(model, args.save+'/'+str(args.task)+'.pt')
torch.save(model.share, args.save+'/share.pt')
torch.save(model.share_classifier, args.save+'/share_classifier.pt')
print("Save model successfully!")
