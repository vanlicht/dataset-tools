import argparse
import cv2
import numpy as np
import os
import shutil

def crop_image_only_outside(img,tol=0):
    # img is 2D or 3D image data
    # tol  is tolerance
    mask = img>tol
    if img.ndim==3:
        mask = mask.all(2)
    m,n = mask.shape
    mask0,mask1 = mask.any(0),mask.any(1)
    col_start,col_end = mask0.argmax(),n-mask0[::-1].argmax()
    row_start,row_end = mask1.argmax(),m-mask1[::-1].argmax()
    return img[row_start:row_end,col_start:col_end]

def crop_dims(img,tol=0,padding=10):
    # img is 2D or 3D image data
    # tol  is tolerance
    mask = img>tol
    if img.ndim==3:
        mask = mask.all(2)
    m,n = mask.shape
    mask0,mask1 = mask.any(0),mask.any(1)
    col_start,col_end = mask0.argmax(),n-mask0[::-1].argmax()
    row_start,row_end = mask1.argmax(),m-mask1[::-1].argmax()
    return (row_start,row_end,col_start,col_end)

def pad_crop(crop_dim,padding,h,w):
    if(crop_dim[0]-padding >= 0):
        crop_dim[0]-=padding
    else:
        crop_dim[0] = 0

    if(crop_dim[1]+padding <= h):
        crop_dim[1]+=padding
    else:
        crop_dim[1] = h

    if(crop_dim[2]-padding >= 0):
        crop_dim[2]-=padding
    else:
        crop_dim[2] = 0

    if(crop_dim[3]+padding <= w):
        crop_dim[3]+=padding
    else:
        crop_dim[3] = w

    return crop_dim

def precrop(img,dims):
    (ih, iw) = img.shape[:2]
    return img[dims[0]:ih-dims[1],dims[2]:iw-dims[3]]

def saveImage(img,path,filename):
    if(args.file_extension == "png"):
        new_file = os.path.splitext(filename)[0] + ".png"
        cv2.imwrite(os.path.join(path, new_file), img, [cv2.IMWRITE_PNG_COMPRESSION, 0])
    elif(args.file_extension == "jpg"):
        new_file = os.path.splitext(filename)[0] + ".jpg"
        cv2.imwrite(os.path.join(path, new_file), img, [cv2.IMWRITE_JPEG_QUALITY, 90])

def removeText(img,dilate_iter):
    scalar = 0.5
    image = img
    (ih, iw) = image.shape[:2]
    resized = cv2.resize(image, (int(iw*scalar),int(ih*scalar)), interpolation = cv2.INTER_NEAREST)
    hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)
    if(args.text_color == 'black'):
        lower = np.array([0, 0, 0])
        upper = np.array([127, 100, 200]) #brown: [200, 150, 180] #black: [127, 100, 200]
    elif(args.text_color == 'brown'):
        lower = np.array([8, 90, 60])
        upper = np.array([30, 235, 180])
    mask = cv2.inRange(hsv, lower, upper)

    # Create horizontal kernel and dilate to connect text characters
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5,3))
    dilate = cv2.dilate(mask, kernel, iterations=dilate_iter)

    # Find contours and filter using aspect ratio
    # Remove non-text contours by filling in the contour
    cnts = cv2.findContours(dilate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cnts[0] if len(cnts) == 2 else cnts[1]
    for c in cnts:
        x,y,w,h = cv2.boundingRect(c)
        ar = w / float(h)
        if (ar < args.text_ar):
            cv2.drawContours(dilate, [c], -1, (0,0,0), -1)

    # 
    # Bitwise dilated image with mask, invert, then OCR
    dilate = cv2.resize(dilate, (iw,ih), interpolation = inter)

    #remove top left
    # dilate[int(ih*0):int(ih*.05),0:int(iw*1.0)] = 0
    #remove middle
    dilate[int(0):int((ih*1.0)-80),0:iw] = 0 #clear errant text capture

    dilate = cv2.cvtColor(dilate,cv2.COLOR_GRAY2RGB)
    result = cv2.bitwise_or(dilate, image)

    return result

def processImage(img,filename):
    padding = args.padding
    (oh, ow) = img.shape[:2]

    if (args.img_debug and (args.process_type != 'contours')):
        saveImage(img,args.output_folder,filename+'-original')

    if(args.precrop):
        dims = [int(item) for item in args.precrop.split(',')]
        img = precrop(img, dims)

        if (args.img_debug):
            saveImage(img,args.output_folder,filename+'-precrop')
    
    if(args.remove_text):
        img = removeText(img,args.dilate_iter)
        rt_img = img.copy()

    if(args.replace_white):
        new_color = [int(item) for item in args.replace_white.split(',')]
        img[np.where((img>=[245,245,245]).all(axis=2))] = new_color

    if(args.process_type == 'contours'):
        print('finds contours in: ' + filename)
        foldername = os.path.join(args.output_folder, filename)

        if not os.path.exists(foldername):
            os.makedirs(foldername)

        if(args.keep_original):
            saveImage(img,foldername,filename+'-original')

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (args.blur_size, args.blur_size), 0)
        
        # ret3,th3 = cv2.threshold(blurred,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        masked = cv2.adaptiveThreshold(blurred,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,11,10)
        kernel = np.ones((3,3),np.uint8)
        dilate = cv2.dilate(masked, kernel, iterations=args.dilate_iter)

        contours, hierarchy = cv2.findContours(dilate, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        if(args.min_width and args.min_height):
            minw = min_width
            minh = min_height
        else:
            minw = minh = args.min_size

        image_number = 0
        drawn = img.copy()
        for contour in contours:
            x,y,w,h = cv2.boundingRect(contour)

            if(args.min_width and args.min_height):
                use = True if (w>args.min_width and h>args.min_height and ((h != oh) and (w != ow)) ) else False
            else:
                use = True if ((w>args.min_size or h>args.min_size) and ((h != oh) and (w != ow)) ) else False
            
            if(use):
                crop_dim = [y,(y+h),x,(x+w)]
                # crop_dim = [(int(1/args.scalar))*x for x in crop_dim]
                crop_dim = pad_crop(crop_dim,args.padding,oh,ow)

                roi = img[crop_dim[0]:crop_dim[1],crop_dim[2]:crop_dim[3]]
                # drawn = cv2.rectangle(drawn, (x, y), (x + w, y + h), (36,255,12), 2)

                fn = filename+'-'+str(image_number)
                saveImage(roi,foldername,fn)
                
                image_number += 1

        if (args.img_debug):
            saveImage(dilate,foldername,filename+'-mask')
            # saveImage(drawn,args.output_folder,filename+'-drawn')

    else:
        resized = cv2.resize(img, (int(w*args.scalar),int(h*args.scalar)), interpolation = inter)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (args.blur_size, args.blur_size), 0)

        if(args.process_type == 'canny'):
            # https://stackoverflow.com/questions/21324950/how-can-i-select-the-best-set-of-parameters-in-the-canny-edge-detection-algorith
            v = np.median(gray)
            #---- Apply automatic Canny edge detection using the computed median----
            sigma = 0.33
            lower = int(max(0, (1.0 - sigma) * v))
            upper = int(min(255, (1.0 + sigma) * v))
            masked = cv2.Canny(blurred, lower, upper)
            crop = crop_image_only_outside(masked)
            crop_dim = crop_dims(masked)
        else:
            masked = cv2.adaptiveThreshold(blurred,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV,31,20)
            crop = crop_image_only_outside(masked)
            crop_dim = crop_dims(masked)

        crop_dim = [(int(1/args.scalar))*x for x in crop_dim]
        crop_dim = pad_crop(crop_dim,args.padding,oh,ow)

        img_out = img[crop_dim[0]:crop_dim[1],crop_dim[2]:crop_dim[3]]
        saveImage(img_out,args.output_folder,filename)

        if (args.img_debug):
            saveImage(masked,args.output_folder,filename+'-mask')
            saveImage(rt_img,args.output_folder,filename+'-rt')

def parse_args():
    desc = "Tools to crop unnecessary space from outside of images" 
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument('--blur_size', type=int, 
        default=3,
        help='size of blur kernel, in pixels (default: %(default)s)')

    parser.add_argument('--dilate_iter', type=int, 
        default=1,
        help='iterations for dilation kernel (increasing can help with tracked type) (default: %(default)s)')

    parser.add_argument('--input_folder', type=str,
        default='./input/',
        help='Directory path to the inputs folder. (default: %(default)s)')

    parser.add_argument('--keep_original', action='store_true',
        help='Save out original image alongside crops (for comparison or debugging)')

    parser.add_argument('--min_size', type=int, 
        default=1024,
        help='minimum width contour, in pixels (default: %(default)s)')

    parser.add_argument('--min_height', type=int, 
        default=None,
        help='minimum height contour, in pixels (default: %(default)s)')

    parser.add_argument('--min_width', type=int, 
        default=None,
        help='minimum width contour, in pixels (default: %(default)s)')

    parser.add_argument('--output_folder', type=str,
        default='./output/',
        help='Directory path to the outputs folder. (default: %(default)s)')

    parser.add_argument('--file_extension', type=str,
        default='png',
        help='Border style to use when using the square process type ["png","jpg"] (default: %(default)s)')

    parser.add_argument('--padding', type=int, 
        default=100,
        help='padding around crop, in pixels. (default: %(default)s)')

    parser.add_argument('--precrop',
        type=str,
        default=None,
        help='crop image before processing (in pixels). Top,Bottom,Left,Right; example: "10,20,10,10" (default: %(default)s)')

    parser.add_argument('--process_type', type=str,
        default='contours',
        help='Options ["canny","threshold","contours"] (default: %(default)s)')

    parser.add_argument('--remove_text', action='store_true',
        help='Remove text from image')

    parser.add_argument('--replace_white',
        type=str,
        default=None,
        help='color to replace text blocks with; use bgr values (default: %(default)s)')

    parser.add_argument('--img_debug', action='store_true',
        help='Save out masked image (for debugging)')

    parser.add_argument('--scalar', type=float, 
        default=.125,
        help='Scalar value. For use with scale process type (default: %(default)s)')

    parser.add_argument('--skip_tags', type=str, 
        default=None,
        help='comma separated color tags (for Mac only) (default: %(default)s)')

    parser.add_argument('--text_ar', type=int, 
        default=3,
        help='aspect ratio for text detection (reduce to find smaller bits of text) (default: %(default)s)')

    parser.add_argument('--text_color', type=str, 
        default='black',
        help='options: black, brown (default: %(default)s)')

    parser.add_argument('--verbose', action='store_true',
        help='Print progress to console.')

    args = parser.parse_args()
    return args

def main():
    global args
    global inter
    args = parse_args()

    os.environ['OPENCV_IO_ENABLE_JASPER']= "true"
    inter = cv2.INTER_CUBIC
    padding = 100

    if os.path.isdir(args.input_folder):
        print("Processing folder: " + args.input_folder)
    elif os.path.isfile(args.input_folder):
        img = cv2.imread(args.input_folder)
        filename = args.input_folder.split('/')[-1]

        if hasattr(img, 'copy'):
            if(args.verbose): print('processing image: ' + filename)  
            processImage(img,os.path.splitext(filename)[0])
    else:
        print("Not a working input_folder path: " + args.input_folder)
        return;

    if(args.skip_tags != None):
        import mac_tag

    if not os.path.exists(args.output_folder):
        os.makedirs(args.output_folder)

    for root, subdirs, files in os.walk(args.input_folder):
        if(args.verbose): print('--\nroot = ' + root)

        for subdir in subdirs:
            if(args.verbose): print('\t- subdirectory ' + subdir)

        for filename in files:
            skipped = False
            file_path = os.path.join(root, filename)
            if(args.verbose): print('\t- file %s (full path: %s)' % (filename, file_path))
            
            if(args.skip_tags != None):
                tags = [str(item) for item in args.skip_tags.split(',')]
                # tags = mac_tag.get(file_path)
                # print(tags)
                for tag in tags:
                    matches = mac_tag.match(tag,file_path)
                    if(file_path in matches):
                        print('skipping file: ' + filename)
                        new_path = os.path.join(args.output_folder, filename)
                        shutil.copy2(file_path,new_path)
                        mac_tag.add([tag],[new_path])
                        skipped = True
                        continue

            if not skipped:
                img = cv2.imread(file_path)

                if hasattr(img, 'copy'):
                    if(args.verbose): print('processing image: ' + filename)  
                    processImage(img,os.path.splitext(filename)[0])

if __name__ == "__main__":
    main()
