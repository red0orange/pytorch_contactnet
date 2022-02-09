import os
import sys
import numpy as np
from numpy import load
import data_utils
import torch
from torch.utils.data import DataLoader, Dataset
from scipy.spatial import KDTree, cKDTree
from scipy.spatial.transform import Rotation as R

def get_dataloader(data_path, data_config=None):
    #data_path = os.path.join(os.getcwd(), data_path)
    dataset = ContactDataset(data_path, data_config)
    dataloader = DataLoader(dataset, batch_size=data_config['batch_size'])
    return dataloader

def extract_point_clouds(self, depth, K, segmap=None, rgb=None, z_range=[0.2,1.8], segmap_id=0, skip_border_objects=False, margin_px=5):
    # NOTE: not currently used!
    """
    Converts depth map + intrinsics to point cloud. 
    If segmap is given, also returns segmented point clouds. If rgb is given, also returns pc_colors.
    Arguments:
        depth {np.ndarray} -- HxW depth map in m
        K {np.ndarray} -- 3x3 camera Matrix
    Keyword Arguments:
        segmap {np.ndarray} -- HxW integer array that describes segeents (default: {None})
        rgb {np.ndarray} -- HxW rgb image (default: {None})
        z_range {list} -- Clip point cloud at minimum/maximum z distance (default: {[0.2,1.8]})
        segmap_id {int} -- Only return point cloud segment for the defined id (default: {0})
        skip_border_objects {bool} -- Skip segments that are at the border of the depth map to avoid artificial edges (default: {False})
        margin_px {int} -- Pixel margin of skip_border_objects (default: {5})
    Returns:
        [np.ndarray, dict[int:np.ndarray], np.ndarray] -- Full point cloud, point cloud segments, point cloud colors
    """
    if K is None:
        raise ValueError('K is required either as argument --K or from the input numpy file')
            
    # Convert to pc 
    pc_full, pc_colors = depth2pc(depth, K, rgb)

    # Threshold distance
    if pc_colors is not None:
        pc_colors = pc_colors[(pc_full[:,2] < z_range[1]) & (pc_full[:,2] > z_range[0])] 
    pc_full = pc_full[(pc_full[:,2] < z_range[1]) & (pc_full[:,2] > z_range[0])]
        
    # Extract instance point clouds from segmap and depth map
    pc_segments = {}
    if segmap is not None:
        pc_segments = {}
        obj_instances = [segmap_id] if segmap_id else np.unique(segmap[segmap>0])
        for i in obj_instances:
            if skip_border_objects and not i==segmap_id:
                obj_i_y, obj_i_x = np.where(segmap==i)
                if np.any(obj_i_x < margin_px) or np.any(obj_i_x > segmap.shape[1]-margin_px) or np.any(obj_i_y < margin_px) or np.any(obj_i_y > segmap.shape[0]-margin_px):
                    print('object {} not entirely in image bounds, skipping'.format(i))
                    continue
            inst_mask = segmap==i
            pc_segment,_ = depth2pc(depth*inst_mask, K)
            pc_segments[i] = pc_segment[(pc_segment[:,2] < z_range[1]) & (pc_segment[:,2] > z_range[0])] #regularize_pc_point_count(pc_segment, grasp_estimator._contact_grasp_cfg['DATA']['num_point'])

    return pc_full, pc_segments, pc_colors

def crop_pcd(pointcloud, center, save_name, radius=0.5):
    '''
    crops a pointcloud to a sphere of specified radius and center 
    (used to make a little demo pointcloud for overfit testing)
    
    returns: np array (Nx3)
    '''
    knn_tree = cKDTree(pointcloud)
    indices = knn_tree.query_ball_point(center, radius)
    #indices = np.delete(indices, np.where(indices==pointcloud.shape[0]))
    cropped_pcd = pointcloud[indices]
    print('cropping', pointcloud.shape, cropped_pcd.shape)
    np.save(save_name, pointcloud)
    #print('float or double?', type(cropped_pcd[0]))
    return cropped_pcd, indices

class ContactDataset(Dataset):
    def __init__(self, data_path, data_config, overfit_test=True):
        self.data = []
        self.data_config = data_config
        data_path = os.fsencode(data_path)
        self.pcreader = data_utils.PointCloudReader(data_path, data_config['batch_size'], pc_augm_config=data_config['pc_augm'], depth_augm_config=data_config['depth_augm'])
        self.data = os.listdir(data_path)
        self.overfit_test = overfit_test
        if self.overfit_test:
            data_file = self.data[0]
            filename = '../acronym/scene_contacts/' + os.fsdecode(data_file)
            self.overfit_scene = load(filename)
            self.gt_contact_info = self.get_contact_info([self.overfit_scene])
                        
    def get_contact_info(self, scene):
        contact_pts, grasp_poses, base_dirs, approach_dirs, offsets, idcs = data_utils.load_contact_grasps(scene, self.data_config)
        gt_contact_info = {}
        gt_contact_info['contact_pts'] = contact_pts
        gt_contact_info['grasp_poses'] = grasp_poses
        gt_contact_info['base_dirs'] = base_dirs
        gt_contact_info['approach_dirs'] = approach_dirs
        gt_contact_info['offsets'] = offsets
        gt_contact_info['idcs'] = idcs
        return gt_contact_info
    
    def __getitem__(self, idx):
        # get positive grasp info
        '''
        grasp_transforms = scene_data['grasp_transforms']
        contact_pts = scene_data['scene_cotact_points']
        contacts1, contacts2 = np.split(contact_pts, 2, axis=1) #split contact points into first and second point
        contacts1, contacts2 = contacts1.reshape(-1, 3), contacts2.reshape(-1, 3) 
        offsets = np.linalg.norm(np.subtract(contacts1, contacts2))
        '''
        if not self.overfit_test:
            data_file = self.data[idx]
            filename = '../acronym/scene_contacts/' + os.fsdecode(data_file)
            scene_data = load(filename)
            self.gt_contact_info = self.get_contact_info([scene_data])
        else:
            scene_data = self.overfit_scene
            
        # render point clouds
        obj_paths = scene_data['obj_paths']
        for i, path in enumerate(obj_paths):
            fixed_path = '../acronym/models/' + path.split('/')[-1]
            obj_paths[i] = fixed_path
        obj_scales = scene_data['obj_scales']
        obj_transforms = scene_data['obj_transforms']
        
        #if not self.overfit_test:
        self.pcreader._renderer.change_scene(obj_paths, obj_scales, obj_transforms)
        self.pc_cam, self.pc_normals, self.camera_pose, self.depth, self.cam_ori = self.pcreader.render_random_scene(estimate_normals=True)

        '''
        pcd_mean = np.mean(self.pc_cam, axis=0)
        pcd_cam_cent = self.pc_cam - pcd_mean
        pcd_cam_cent_rot = np.matmul(self.camera_pose[:-1, :-1], pcd_cam_cent.T).T
        y_rot_mat = R.from_euler('xyz', [0, np.pi, 0]).as_matrix()
        z_rot_mat = R.from_euler('xyz', [0, 0, np.pi/2]).as_matrix()
        pcd_world = pcd_cam_cent_rot + pcd_mean
        
        # pcd_world = pcd_cam_cent_rot + self.camera_pose[:-1, -1] + pcd_mean
        
        rand_pt = [0, 0, 0]
        # self.pc, _ = crop_pcd(pcd_world, rand_pt, 'obs_pcd')
        self.pc, _ = crop_pcd(pcd_cam_cent_rot, rand_pt, 'obs_pcd')
        # self.pc, _ = crop_pcd(pcd, rand_pt, 'obs_pcd')
        self.gt_contact_info['contact_pts'], crop_idcs = crop_pcd(self.gt_contact_info['contact_pts'][0], rand_pt, 'gt_pcd')
        self.gt_contact_info['grasp_poses'] = self.gt_contact_info['grasp_poses'][:, crop_idcs]
        self.gt_contact_info['base_dirs'] = self.gt_contact_info['base_dirs'][:, crop_idcs]
        self.gt_contact_info['approach_dirs'] = self.gt_contact_info['approach_dirs'][:, crop_idcs]
        self.gt_contact_info['offsets'] = self.gt_contact_info['offsets'][:, crop_idcs]
        self.gt_contact_info['idcs'] = crop_idcs
        '''
        pcd = self.pc_cam[:, :3]
        pcd_normals = self.pc_normals[:, :3]
        
        return torch.Tensor(pcd).float(), torch.Tensor(pcd_normals).float(), self.camera_pose, self.gt_contact_info

    def __len__(self):
        return len(self.data)
