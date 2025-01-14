# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys
import os

import matplotlib.pyplot as plt
from matplotlib.patches import Wedge
import numpy as np
import shutil
from imageio import imread, imsave
from scipy.signal import medfilt, argrelmin
from skimage.transform import iradon, iradon_sart, downscale_local_mean
from scipy.ndimage.filters import median_filter

from lightct.plot_funcs import recentre_plot, SetAngleInteract


class LoadProjections(object):

    def __init__(self, folder, im_type='tif'):
        """
        Load a previously acquired series of projections for analysis and
        reconstruction.

        # folder:    Path to folder where projections are stored. Reconstructed
                     slices will also be saved here.
        """
        self.folder = os.path.split(os.path.abspath(folder))[0]
        self.p0 = 0
        self.cor_offset = 0
        self.crop = None, None, None, None
        self.num_images = None
        self.angles = None

        files = [f for f in os.listdir(folder) if f[-4:] == '.%s' % im_type]
        im_shape = imread(os.path.join(folder, files[0])).shape
        self.im_stack = np.zeros(im_shape + (len(files), ))
        for idx, fname in enumerate(files):
                sys.stdout.write('\rProgress: [{0:20s}] {1:.0f}%'.format('#' *
                                 int(20*(idx + 1) / len(files)),
                                 100*((idx + 1)/len(files))))
                sys.stdout.flush()
                f = os.path.join(folder, fname)
                self.im_stack[:, :, idx] = imread(f)

        self.height = self.im_stack.shape[0]
        self.width = self.im_stack.shape[1]
        
    def plot_histogram(self, proj=5):
        """
        Plots histogram of pixel intensity for specified projection.
        
        # proj:       Number of projection to display/assess (int)
        """
        histogram = np.histogram(self.im_stack[:, :, proj], 255)
        plt.plot(histogram[0])
        plt.show()

    def set_angles(self, num_images, ang_range=360, p0=5):
        """
        Manually define the number of images in 360 degrees. 

        # num_images: Specify number of images
        # ang_range:  Specify angular range (must be multiple of 180)
        # p0:         Projection to use as initial or reference projection.
                      Recommended to be greater than 1 (due to acquisition
                      spacing issues in initial projections)

        """
        self.p0 = p0

        error = 'Images must cover a rotational range of 180 or 360 deg'
        assert (ang_range == 180) or (ang_range == 360), error
        self.angles = np.linspace(0, ang_range, num_images)
        self.num_images = num_images
        
    def auto_set_angles(self, est_nproj, p0=5, downscale=True, plot=True):
        """
        Attempts to automatically locate image at 360 degrees (and multiples
        of 360 degrees). Alignment based on difference calculation between 
        reference projection each subsequent projections. 
        
        # est_nproj:  Estimated number of projections in 360 degrees
        # p0:         Projection to use as initial or reference projection.
                      Recommended to be greater than 1 (due to acquisition
                      spacing issues in initial projections)
        # plot:       Plot the difference results
        """
        order = est_nproj // 2
        self.p0 = p0
        
        diff = np.nan * np.ones((self.im_stack.shape[-1] - p0))
        proj_nums = range(p0, self.im_stack.shape[-1])

        ref = self.im_stack[:, :, p0]
        data = self.im_stack[:, :, p0:]
        
        tmp = data - ref[:, :, np.newaxis]
        tmp = tmp.reshape(-1, tmp.shape[-1])
    
        diff = tmp.std(axis=0)

        minimas = argrelmin(diff, order=order)
        self.num_images = minimas[0][0] + 1
        self.angles = np.linspace(0, 360, self.num_images, dtype=int)
        
        if plot:
            fig, ax = plt.subplots()
            fig.canvas.set_window_title('Projection Analysis')
            ax.plot(proj_nums, diff)
            ax.plot(minimas[0] + p0, np.array(diff)[minimas], 'r*')
            ax.plot([minimas[0][0] + p0, minimas[0][0] + p0],
                     [0, np.max(diff)], 'r--')
            ax.set_xlabel('Image number')
            ax.set_ylabel('Thresholded Pixels Relative to Image 1')
            ax.text(minimas[0][0] + p0, np.max(diff), r'$360^{\circ}$',
                     horizontalalignment='center', verticalalignment='bottom')
        plt.show()
                     
        print('\n%i images in a 360 rotation.\n\nIf this is incorrect '
              'either rerun with a different value for est_nproj or use the '
              'manual method.' % self.num_images)
        
    def set_centre(self, cor):
        """
        Define the centre of rotation.
        
        # window:     Window width to search across (pixels).
        """
        self.cor_offset = cor
        
    def auto_centre(self, window=400, downsample_y=2, plot=True):
        """
        Automatic method for finding the centre of rotation.
        
        # window:     Window width to search across (pixels).
        """
        downsample = (downsample_y, 1)
        half_win = window // 2
        win_range = range(-half_win, half_win)
        
        # Compare ref image with flipped 180deg counterpart
        ref_image = self.im_stack[:, half_win:-half_win, self.p0]
        ref = downscale_local_mean(ref_image, downsample)
        im_180_image = self.im_stack[:, :, self.num_images // 2 + self.p0]
        im_180 = downscale_local_mean(im_180_image, downsample)
        flipped = np.fliplr(im_180)
        
        diff = np.nan * np.zeros(len(win_range))

        # Flip win_range as we are working on flipped data
        for idx, i in enumerate(win_range[::-1]):
            
            cropped = flipped[:, half_win + i: -half_win + i]
            tmp = cropped - ref
            diff[idx] = tmp.std()
            
        minima = np.argmin(diff)
        self.cor_offset = win_range[minima]
        print('COR = %i' % self.cor_offset)

        if plot:
            fig, ax = plt.subplots()
            fig.canvas.set_window_title('Centre Analysis')
            ax.plot([i for i in win_range], diff)
            ax.plot(self.cor_offset, np.min(diff), '*')
            ax.set_ylabel('Standard deviation (original v 180deg flipped)')
            ax.set_xlabel('2 * Centre correction (pixels)')
            im_copy = np.copy(self.im_stack[:, :, self.p0])
            recentre_plot(im_copy, self.cor_offset)
        
    def manual_set_angles(self, p0=5):
        """
        Manually define the number of images in 360 degrees. Defaults to 
        interactive mode in which images can be compared against initial, 
        reference image.

        # p0:         Projection to use as initial or reference projection.
                      Recommended to be greater than 1 (due to acquisition
                      spacing issues in initial projections)
        """
        self.p0 = p0

        interact = SetAngleInteract(self.im_stack, self.p0)
        interact.interact()
        self.angles = interact.angles
        self.num_images = interact.num_images
        
    def set_crop(self, width, top, bottom, plot=True):
        """
        Crop...
        """
        if self.cor_offset >= 0:
            images = self.im_stack[:, self.cor_offset:]
        else:
            images = self.im_stack[:, :self.cor_offset]
            
        self.crop = ()
        for i in (width, -width, top, -bottom): 
            self.crop += (None,) if i == 0 else (i,)

        
        if plot:
            left, right, top, bottom = self.crop
            
            images_per_degree = self.num_images / 360
            degrees = [0, 60, 120]
            image_nums = [int(images_per_degree * deg) for deg in degrees]
            fig, ax_array = plt.subplots(1, 3, figsize=(8, 3))
            fig.canvas.set_window_title('Crop Output')
            for ax, i in zip(ax_array, image_nums):
                ax.imshow(images[top:bottom, left:right, i])
                ax.text(0.15, 0.88, r'$%0d^\circ$' % (i * 360/self.num_images), 
                        size=14, transform = ax.transAxes,
                        va = 'center', ha = 'center')
                ax.xaxis.set_ticklabels([])
                ax.yaxis.set_ticklabels([])
            fig.tight_layout()
            plt.show()
            

    def reconstruct(self, downsample=(4, 4), crop=True, median_filter=False, 
                    kernel=9, recon_alg='fbp', sart_iters=1, threshold=0.5,
                    crop_circle=False, save=True, fancy_out=False, average=False):
        """
        Reconstruct the data using a radon transform. Reconstructed slices
        saved in folder specified upon class creation.

        # downsample: Downsample (local mean) data before reconstructing.
                      Specify mean kernel size (height, width).
        # pre_filter: If True apply median filter to data before reconstructing
        # kernel:     Kernel size to use for median filter
        """

        if self.cor_offset >= 0:
            images = self.im_stack[:, self.cor_offset:]
        else:
            images = self.im_stack[:, :self.cor_offset]

        # option to average over multiple rotations of images
        if average:
            rots = (images.shape[-1]-self.p0) // self.num_images
            new_shape = images.shape[0:2] + (self.num_images, rots)
            images = np.reshape(images[:,:,self.p0:rots*self.num_images + self.p0], new_shape)
            images = images.mean(axis=3)
        else:
            images = images[:, :, self.p0:self.num_images + self.p0]

        
        if crop:
            left, right, top, bottom = self.crop
            images = images[top:bottom, left:right]
            
            images = downscale_local_mean(images, downsample + (1, ))
        recon_height, recon_width = images.shape[:2]
        self.recon_data = np.zeros((recon_width, recon_width, recon_height))

        if median_filter:
            print('Applying median filter...')
            for i in range(images.shape[-1]):
                sys.stdout.write('\rProgress: [{0:20s}] {1:.0f}%'.format('#' *
                                 int(20 * (i + 1) / images.shape[-1]),
                                 100 * ((i + 1) / images.shape[-1])))
                sys.stdout.flush()
                images[:, :, i] = medfilt(images[:, :, i], kernel_size=kernel)

        print('\nReconstructing...')
        if save:            
            save_folder = os.path.join(self.folder, 'reconstruction')
            
            if not os.path.exists(save_folder):
                os.makedirs(save_folder)
            for the_file in os.listdir(save_folder):
                file_path = os.path.join(save_folder, the_file)
                if os.path.isfile(file_path):
                        os.unlink(file_path)

        if fancy_out:
            fig, ax = plt.subplots(figsize=(4, 4))
            fig.canvas.set_window_title('Reconstruction')
            patch = Wedge((.5, .5), .375, 90, 90, width=0.1)
            ax.add_patch(patch)
            ax.axis('equal')
            ax.set_xlim([0, 1])
            ax.set_ylim([0, 1])
            ax.axis('off')
            t = ax.text(0.5, 0.5, '0%%', fontsize=15, ha='center', va='center')

        for j in range(recon_height):
            # Update figure every other slice
            if fancy_out and j % 2 == 0:
                patch.set_theta1(90 - 360 * (j + 1) / recon_height)
                progress = 100 * (j + 1) / recon_height
                t.set_text('%02d%%' % progress)
                plt.pause(0.001)
            else:
                sys.stdout.write('\rProgress: [{0:20s}] {1:.0f}%'.format('#' *
                                 int(20 * (j + 1) / recon_height),
                                 100 * ((j + 1) / recon_height)))
                sys.stdout.flush()
            sino_tmp = np.squeeze(images[j, :, :])
            
            if recon_alg == 'sart':
                image_tmp = iradon_sart(sino_tmp, theta=self.angles)
                for i in range(sart_iters - 1):
                    image_tmp = iradon_sart(sino_tmp, theta=self.angles, 
                                            image=image_tmp)
            elif recon_alg == 'visualhulls':
                image_tmp = self.visualhulls_recon(sino_tmp, threshold)
                
            else:
                #sino_tmp = self.binarise_sino(sino_tmp)
                image_tmp = iradon(sino_tmp, theta=self.angles, 
                                   filter_name=None, circle=True)
#            if crop_circle:
#                image_tmp = image_tmp[w0:wf, w0:wf]
                
            self.recon_data[:, :, j] = image_tmp
            
        if crop_circle:
            w = int((recon_width**2 / 2)**0.5) 
            w = w if (w - recon_width) % 2 == 0 else w - 1
            w0 = int((recon_width - w) / 2 )
            wf = int(w0 + w)
            self.recon_data = self.recon_data[w0:wf, w0:wf]
            
        if save:    
            for j in range(recon_height):
                image_tmp = self.recon_data[:, :, j]
                imsave(os.path.join(save_folder, '%04d.tif' % j), image_tmp)

            import h5py
            with h5py.File(os.path.join(save_folder, 'recon2.h5'), 'w') as f:
                f['data'] = self.recon_data

        if fancy_out:
            plt.close()


    def visualhulls_recon(self, sino, threshold):
        sino = -np.log(sino + 0.00000001)
        sino = self.binarise_sino(np.transpose(sino), threshold)
        data_shape = (sino.shape[1], sino.shape[1])
        centre = data_shape[0] // 2
        full = np.ones(data_shape)        
        for i in range(self.num_images):
            mapping_array = self._mapping_array(
                data_shape, centre, np.deg2rad(self.angles[i]))
            mapping_array = np.clip(mapping_array.astype('int') + centre, 0,
                                     sino.shape[1]-1).astype('int')
            mask = sino[i, :][mapping_array]
            full -= 1-mask
        data_range = full.max() - full.min()
        full += data_range // 4
        full[full < 0.5] = 0
        return full
    
        
    def binarise_sino(self, orig_sino, threshold):
        sino = np.zeros_like(orig_sino)
        sino[orig_sino > threshold] = 1  # default threshold is 0.5
        return median_filter(sino, size=2)
        

    def _mapping_array(self, data_shape, centre, theta):
        x, y = np.meshgrid(np.arange(-centre, data_shape[0] - centre),
                           np.arange(-centre, data_shape[1] - centre))
        return x*np.cos(theta) - y*np.sin(theta)
        