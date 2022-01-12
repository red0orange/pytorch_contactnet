import numpy as np
import math

def farthest_point_downsample(pointcloud, k):
    '''                                                                                                                           
    pointcloud (numpy array): cartesian points, shape (N, 3)                                                                      
    k (int): number of points to sample                                                                                           
                                                                                                                                  
    sampled_cloud (numpy array): downsampled points, shape (k, 3)                                                                 
    '''
    start_ind = np.random.randint(0, len(pointcloud)) # pick a random point in the cloud to start                                 
    sampled_cloud = np.array([pointcloud[start_ind]])
    pointcloud = np.delete(pointcloud, start_ind, axis=0)
    mindists = np.full(len(pointcloud), np.inf) # make a list of minimum distances to samples for each point                      
    for i in range(k):
        last_sample = sampled_cloud[-1]
        ptdists = ((pointcloud-last_sample)**2).sum(axis=1) # distances between each point and most recent sample
        mindists = np.minimum(ptdists, mindists)
        min_ind = np.argmax(mindists)
        sampled_cloud = np.append(sampled_cloud, [pointcloud[min_ind]], axis=0)
        pointcloud = np.delete(pointcloud, min_ind, axis=0)
        mindists = np.delete(mindists, min_ind, axis=0)
    return sampled_cloud
