# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys
import time
import os

import cv2
import matplotlib
import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.widgets import Slider, Button
import numpy as np
from scipy.misc import imread, imsave
from scipy.signal import medfilt, argrelmin
from skimage import color
from skimage.transform import iradon, downscale_local_mean


class TomoScan(object):
    
    def __init__(self, num_projections, save_folder, camera_port=0,
                 wait=0, save=True):
        """
        Note that for the subsequent functionality to work, the number of 
        projections must be great enough to ensure that a rotational 
        range > 360 degrees is captured.
        """
        self.folder = save_folder
        self.p0 = 0
        self.cor_offset = 0
        self.num_images = 0
        self.angles = None
        self.recon_data = None

        camera = cv2.VideoCapture(camera_port)
        retval, im = camera.read()
        try:
            dims = im[:, :, 2].shape + (num_projections, )
        except TypeError:
            error = ("Camera returning None. Check camera settings (port) and"
                     " ensure camera is not being run by other software.")
            raise TypeError(error)
        self.im_stack = np.zeros(dims)

        for i in range(num_projections):
            retval, im = camera.read()
            self.im_stack[:, :, i] = color.rgb2hsv(im)[:, :, 2]
            sys.stdout.write("\rProgress: [{0:20s}] {1:.0f}%".format('#' * 
                             int(20*(i + 1) / num_projections),
                             100*((i + 1)/num_projections)))
            sys.stdout.flush()
            time.sleep(wait)
        del camera

        self.height = self.im_stack.shape[0]
        self.width = self.im_stack.shape[1]

        if save:
            save_folder = os.path.join(self.folder, 'projections')
            if not os.path.exists(save_folder):
                os.makedirs(save_folder)
            for idx in range(self.im_stack.shape[-1]):
                fpath = os.path.join(save_folder, '%04d.tif' % idx)
                imsave(fpath, self.im_stack[:, :, idx])

    def plot_histogram(self, projection=5):
        """
        Plots histogram of pixel intensity for specified projection.
        
        # projection: Projection number (int)
        """
        histogram = np.histogram(self.im_stack[:, :, projection], 255)
        plt.plot(histogram[0])
        plt.show()
        
    def auto_set_angles(self, order, p0=5, plot=True):
        """
        Attempts to automatically locate image at 360 degrees (and multiples
        of 360 degrees). Alignment based on difference calculation between 
        reference projection each subsequent projections. 
        
        # p0:         Projection to use as initial or reference projection.
                      Recommended to be greater than 1 (due to acquisition
                      spacing issues in initial projections)
        # order:      Window in which to search for minimas in the
                      difference calculations - should be approx equal to 
                      (number of projections in 360) / 2
        # plot:       Plot the difference results
        """
        self.p0 = p0
        ref = downscale_local_mean(self.im_stack[:, :, p0], (3, 3))
        diff = np.nan * np.ones((self.im_stack.shape[-1] - p0))
        proj_nums = range(p0, self.im_stack.shape[-1])
        for idx, i in enumerate(proj_nums):
            current = downscale_local_mean(self.im_stack[:, :, i], (3, 3))
            tmp = current - ref
            diff[idx] = tmp.std()
        minimas = argrelmin(np.array(diff), order=order)
        print(minimas)
        self.num_images = minimas[0][0] + 1
        self.angles = np.linspace(0, 360, self.num_images, dtype=int)
        
        if plot:
            plt.figure()
            plt.plot(proj_nums, diff)
            plt.plot(minimas[0] + p0, np.array(diff)[minimas], 'r*')
            plt.plot([minimas[0][0] + p0, minimas[0][0] + p0],
                     [0, np.max(diff)], 'r--')
            plt.xlabel('Image number')
            plt.ylabel('Thresholded Pixels Relative to Image 1')
            plt.text(minimas[0][0] + p0, np.max(diff), r'$360^{\circ}$',
                     horizontalalignment='center', verticalalignment='bottom')
        plt.show()
                     
        print('\n%i images in a 360 rotation. \n\n If this is incorrect '
              'either rerun with a different value for order or use the manual'
              ' method.' % self.num_images)
        
    def auto_centre(self, window=400):
        """
        Automatic method for finding the centre of rotation.
        
        # window:     Window width to search across (pixels).
        """
        half_win = window // 2
        win_range = range(-half_win, half_win)
        
        ref = self.im_stack[:, half_win:-half_win, self.p0]
        im_180 = self.im_stack[:, :, int(self.num_images / 2) + self.p0]
        flipped = np.fliplr(im_180)
        
        diff = np.nan * np.zeros(len(win_range))
        
        for idx, i in enumerate(win_range):
            
            cropped = flipped[:, half_win + i: -half_win + i]
            tmp = cropped - ref
            diff[idx] = tmp.std()
        
        minima = np.argmin(diff)
        self.cor_offset = win_range[minima]

        plt.plot(win_range, diff)
        plt.plot(self.cor_offset, np.min(diff), '*')
        plt.ylabel('Standard deviation (original v 180deg flipped)')
        plt.xlabel('Cropped pixels')
        
        fig, ax_array = plt.subplots(1, 2, figsize=(10, 6))
        image = np.copy(self.im_stack[:, :, self.p0])
        if self.cor_offset <= 0:
            poly_pnts = [[self.width + self.cor_offset, 0], [self.width, 0],
                         [self.width, self.height],
                         [self.width + self.cor_offset, self.height]]
        else:
            poly_pnts = [[0, 0], [self.cor_offset, 0],
                         [self.cor_offset, self.height], [0, self.height]]
        ax_array[0].imshow(image)
        centre = self.width / 2 - self.cor_offset / 2
        ax_array[0].plot([centre, centre], [0, self.height], 'k-',
                         linewidth=2, label='New COR')
        ax_array[0].plot([self.width / 2, self.width / 2],
                         [0, self.height], 'r-', linewidth=2, label='Old COR')
        ax_array[0].legend()
        ax_array[0].set_xlim([0, image.shape[1]])
        ax_array[0].set_ylim([image.shape[0], 0])

        if self.cor_offset <= 0:
            image = np.copy(self.im_stack[:, -self.cor_offset:, self.p0])
        else:
            image = np.copy(self.im_stack[:, :-self.cor_offset, self.p0])
            
        ax_array[1].imshow(image)
        ax_array[1].plot([image.shape[1]/2, image.shape[1]/2],
                         [0, self.height], 'k-', linewidth=2, label='New COR')
        ax_array[1].legend()
        
        ax_array[1].set_xlim([0, image.shape[1]])
        ax_array[1].set_ylim([image.shape[0], 0])
        
        ax_array[0].add_patch(patches.Polygon(poly_pnts, closed=True,
                              fill=False, hatch='///', color='k'))
        ax_array[0].set_title('Uncropped')
        ax_array[1].set_title('Cropped and centred')

        plt.show()

    def manual_set_angles(self, interact=True, p0=5,
                          num_images=None, ang_range=None):
        """
        Manually define the number of images in 360 degrees. Defaults to 
        interactive mode in which images can be compared against initial, 
        reference image.

        # interact:   Run in interactive mode (True/False)
        # p0:         Projection to use as initial or reference projection.
                      Recommended to be greater than 1 (due to acquisition
                      spacing issues in initial projections)
        # num_images: If not in interact mode, manually specify number 
                      of images
        # ang_range:  If not in interact mode, manually specify angular range 
                      of images (must be multiple of 180)
        """
        self.p0 = p0

        if interact:
            backend = matplotlib.get_backend()
            err = ("Matplotlib running inline. Plot interaction not possible."
                   "\nTry running %matplotlib in the ipython console (and "
                   "%matplotlib inline to return to default behaviour). In "
                   "standard console use matplotlib.use('TkAgg') to interact.")
                     
            assert backend != 'module://ipykernel.pylab.backend_inline', err
            fig, ax_array = plt.subplots(1, 2, figsize=(10, 5))
            
            ax_slider = plt.axes([0.2, 0.07, 0.5, 0.05])  
            ax_button = plt.axes([0.81, 0.05, 0.1, 0.075])
            
            ax_array[0].imshow(self.im_stack[:, :, p0])
            ax_array[1].imshow(self.im_stack[:, :, p0])
            ax_array[0].axis('off')
            ax_array[1].axis('off')
            fig.tight_layout()
            fig.subplots_adjust(bottom=0.2)
            nfiles = self.im_stack.shape[-1] + 1
            window_slider = Slider(ax_slider, 'Image', p0, nfiles, valinit=0)
            store_button = Button(ax_button, r'Save - 360')
            
            def slider_update(val):
                ax_array[1].imshow(self.im_stack[:, :, int(window_slider.val)])
                window_slider.valtext.set_text('%i' % window_slider.val)
                fig.canvas.draw_idle()
                
            window_slider.on_changed(slider_update)
            
            def store_data(label):
                # Check this is correct - proj_ref!!!
                self.num_images = int(window_slider.val) - p0 + 1
                self.angles = np.linspace(0, 360, self.num_images)
                plt.close()
                
            store_button.on_clicked(store_data)
            plt.show()
            return window_slider, store_button

        else:
            error = 'Images must cover a rotational range of 180 or 360 deg'
            assert (ang_range == 180) or (ang_range == 360), error
            self.angles = np.linspace(0, ang_range, num_images)
            self.im_stack = self.im_stack[:, :, :num_images]
        
    def reconstruct(self, downsample=(4, 4, 1), pre_filter=True, kernel=9):
        
        if self.cor_offset <= 0:
            images = self.im_stack[:, -self.cor_offset:,
                                   self.p0:self.num_images + self.p0]
        else:
            images = self.im_stack[:, :-self.cor_offset,
                                   self.p0:self.num_images + self.p0]
            
        images = downscale_local_mean(images, downsample)
        
        if pre_filter is not False:
            for i in range(images.shape[-1]): 
                images[:, :, i] = medfilt(images[:, :, i], kernel_size=kernel)

        for j in range(self.height):
            sinotmp = np.squeeze(images[j, :, :])
            imagetmp = iradon(sinotmp, theta=self.angles,
                              filter=None, circle=True)

            self.recon_data[:, :, j] = imagetmp
            save_folder = os.path.join(self.folder, 'reconstruction')
            if not os.path.exists(save_folder):
                os.makedirs(save_folder)
            imsave(os.path.join(save_folder, '%04d.tif' % j), imagetmp)

        
class LoadProjections(TomoScan):

    def __init__(self, load_folder):

        self.folder = load_folder
        files = [f for f in os.listdir(load_folder) if f[-4:] == '.tif']
        im_shape = imread(os.path.join(self.folder, files[0])).shape
        self.im_stack = np.zeros(im_shape + (len(files), ))
        for idx, fname in enumerate(files):
            sys.stdout.write("\rProgress: [{0:20s}] {1:.0f}%".format('#' * 
                             int(20*(idx + 1) / len(files)),
                             100*((idx + 1)/len(files))))
            sys.stdout.flush()
            f = os.path.join(self.folder, fname)
            self.im_stack[:, :, idx] = imread(f)

        self.p0 = 0
        self.cor_offset = 0
        self.num_images = 0
        self.angles = None
        self.height = self.im_stack.shape[0]
        self.width = self.im_stack.shape[1]
