function gen_trans_im(in_mat_path, out_mat_path)
%GEN_TRANS_IM Summary of this function goes here
%   Detailed explanation goes here

load(in_mat_path);
gX = double(labels);
gY= images';
%[coeff, XX] = pca(gX);
XX = gX;

m = size(XX,2);
%[Su, Se, mean_a, mean_l] = global_model(XX(:,1:m), gY);
%save('cifar10_global_model.mat','Su','Se','mean_a','mean_l');
load('cifar10_global_model.mat');

idx1 = gY==1;
idx0 = gY==0;
XX0 = XX(idx0,1:m);
XX1 = XX(idx1,1:m);
n0 = size(XX0,1);
n1 = size(XX1,1);
u1 = statistic_mean(XX1,Su, Se, mean_a);
u0 = statistic_mean(XX0,Su, Se, mean_a);
E0 = XX0-repmat(u0,[n0,1]);
E1 = XX1-repmat(u1,[n1,1]);
nX0 = repmat(u0,[n1,1])+E1;


save(out_mat_path,'nX0');

end

