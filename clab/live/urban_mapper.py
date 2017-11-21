# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals
import torch
import glob
import numpy as np  # NOQA
import ubelt as ub
import os  # NOQA
from os.path import join, splitext, basename  # NOQA
from clab import util
from clab.torch import xpu_device
from clab.torch import models
from clab.util import imutil
from clab.live.urban_train import get_task, SSegInputsWrapper


def urban_mapper_eval_dataset():
    from clab import preprocess
    task = get_task('urban_mapper_3d')
    eval_fullres = task.load_fullres_inputs('testing')
    datadir = ub.ensuredir((task.workdir, 'eval_data'))
    prep = preprocess.Preprocessor(datadir)
    eval_part1_scale = prep.make_parts(eval_fullres, scale=1, clear=0)

    eval_dataset = SSegInputsWrapper(eval_part1_scale, task, colorspace='RGB')
    eval_dataset.with_gt = False
    eval_dataset.inputs.make_dumpsafe_names()
    eval_dataset.fullres = eval_fullres
    eval_dataset.tag = 'eval'

    return eval_dataset


def hack_urban_mapper_eval_submission():
    """
    hacked together script to get the testing data and run prediction for submission
    """

    # train_dpath = ub.truepath(
    #     '~/remote/aretha/data/work/urban_mapper/arch/unet/train/input_4214-yxalqwdk/solver_4214-yxalqwdk_unet_vgg_nttxoagf_a=1,n_ch=5,n_cl=3')
    # load_path = get_snapshot(train_dpath, epoch=202)

    if False:
        train_dpath = ub.truepath(
            '~/remote/aretha/data/work/urban_mapper/arch/unet/train/'
            'input_8438-haplmmpq/solver_8438-haplmmpq_unet_None_kvterjeu_a=1,c=RGB,n_ch=5,n_cl=3')
        load_path = get_snapshot(train_dpath, epoch=258)

        eval_dataset = urban_mapper_eval_dataset()
        eval_dataset.center_inputs = eval_dataset._original_urban_mapper_normalizer()

    elif True:
        train_dpath = ub.truepath(
            '~/data/work/urban_mapper2/arch/unet/train/input_4214-guwsobde/'
            'solver_4214-guwsobde_unet_mmavmuou_eqnoygqy_a=1,c=RGB,n_ch=5,n_cl=4/')

        eval_dataset = urban_mapper_eval_dataset()
        eval_dataset.center_inputs = eval_dataset._original_urban_mapper_normalizer()

    # load_path = get_snapshot(train_dpath)

    pharn = PredictHarness(eval_dataset)
    pharn.hack_dump_path(load_path)
    pharn.load_snapshot(load_path)
    pharn.run()

    mode = 'pred'
    # mode = 'pred_crf'
    restitched_pred = pharn._restitch_type(mode, blend='vote')

    # if True:
    #     _restitch_type(test_dump_dpath, 'blend_pred', blend=None)
    #     _restitch_type(test_dump_dpath, 'blend_pred_crf', blend=None)

    restitched_pred = eval_dataset.fullres.align(restitched_pred)

    def compact_idstr(dict_):
        short_keys = util.shortest_unique_prefixes(dict_.keys())
        short_dict = ub.odict(sorted(zip(short_keys, dict_.values())))
        idstr = ub.repr2(short_dict, nobr=1, itemsep='', si=1, nl=0,
                         explicit=1)
        return idstr

    # Convert to submission output format
    post_kw = dict(k=15, n_iters=1, dist_thresh=5, watershed=True)
    # post_kw = dict(k=0, watershed=False)
    post_idstr = compact_idstr(post_kw)

    lines = []
    for ix, fpath in enumerate(ub.ProgIter(restitched_pred, label='rle')):
        pred = imutil.imread(fpath)
        cc_labels = eval_dataset.task.instance_label(pred, **post_kw)

        fname = splitext(basename(fpath))[0]
        (width, height), runlen = imutil.run_length_encoding(cc_labels)

        lines.append(fname)
        lines.append('{},{}'.format(width, height))
        lines.append(','.join(list(map(str, runlen))))

    text = '\n'.join(lines)
    suffix = '_'.join(pharn.test_dump_dpath.split('/')[-2:]) + '_' + mode + '_' + post_idstr
    fpath = join(pharn.test_dump_dpath, 'urban_mapper_test_pred_' + suffix + '.txt')
    ub.writeto(fpath, text)

    # Submission URL
    # https://community.topcoder.com/longcontest/
    # https://community.topcoder.com/longcontest/?module=Submit&compid=57607&rd=17007&cd=15282

    # from os.path import dirname, split
    # for ix, fpath in enumerate(ub.ProgIter(restitched_pred[0:10], label='blend instance')):
    #     base_dpath, mode = split(dirname(fpath))
    #     output_dpath = ub.ensuredir(join(base_dpath, 'blend_instance_' + mode))
    #     output_fpath = join(output_dpath, basename(fpath))

    #     pred = imutil.imread(fpath)
    #     cc_labels = eval_dataset.task.instance_label(pred, k=7, n_iters=1,
    #                                                  watershed=True)
    #     big_orig_fpath = eval_dataset.fullres.im_paths[ix]
    #     big_orig = imutil.imread(big_orig_fpath)
    #     big_blend_instance_pred = eval_dataset.task.instance_colorize(cc_labels, big_orig)
    #     imutil.imwrite(output_fpath, big_blend_instance_pred)

    """
    Leaderboards:
        https://community.topcoder.com/longcontest/?module=ViewStandings&rd=17007
    """


def get_snapshot(train_dpath, epoch='recent'):
    snapshots = sorted(glob.glob(train_dpath + '/*/_epoch_*.pt'))
    if epoch is None:
        epoch = 'recent'

    if epoch == 'recent':
        load_path = snapshots[-1]
    else:
        import parse
        snapshot_nums = [parse.parse('{}_epoch_{num:d}.pt', path).named['num']
                         for path in snapshots]
        load_path = dict(zip(snapshot_nums, snapshots))[epoch]
    return load_path


def evaulate_internal_testset():
    """
    Working with the testing set (don't submit with this)
    """
    from clab.live.urban_train import load_task_dataset
    datasets = load_task_dataset('urban_mapper_3d')
    test_dataset = datasets['test']
    test_dataset.with_gt = False
    test_dataset.inputs.make_dumpsafe_names()
    test_dataset.center_inputs = test_dataset._original_urban_mapper_normalizer()
    test_dataset.tag = 'test'

    # 3D3__epoch_00000202

    train_dpath = ub.truepath(
        '~/remote/aretha/data/work/urban_mapper/arch/unet/train/input_4214-yxalqwdk/solver_4214-yxalqwdk_unet_vgg_nttxoagf_a=1,n_ch=5,n_cl=3')
    load_path = get_snapshot(train_dpath, epoch=202)

    pharn = PredictHarness(test_dataset)
    pharn.hack_dump_path(load_path)
    # pharn.load_snapshot(load_path)
    # pharn.run()

    # hack
    if 0:
        for mode in ['blend_pred', 'blend_pred_crf']:
            restitched_paths = pharn._restitch_type(mode, blend=None)

        paths = {}
        for mode in ['pred', 'pred_crf']:
            restitched_paths = pharn._restitch_type(mode, blend='vote')
            for big_pred_fpath in ub.ProgIter(restitched_paths, label='open ' + mode):
                big_pred = imutil.imread(big_pred_fpath)

                k = 7
                n_iters = 1
                new_fpath = big_pred_fpath.replace('/' + mode + '/', '/' + mode + '_open{}x{}/'.format(k, n_iters))
                new_blend_fpath = big_pred_fpath.replace('/' + mode + '/', '/blend_' + mode + '_open{}x{}/'.format(k, n_iters))
                ub.ensuredir(os.path.dirname(new_fpath))
                ub.ensuredir(os.path.dirname(new_blend_fpath))

                pred2 = (test_dataset.task.instance_label(big_pred, k=k,
                                                          n_iters=n_iters,
                                                          watershed=False) > 0
                         ).astype(np.int8)
                imutil.imwrite(new_fpath, pred2)

                big_im_fname = basename(big_pred_fpath).replace('.png', '_RGB.tif')
                big_orig_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', big_im_fname)
                big_orig = imutil.imread(big_orig_fpath)

                big_blend_instance_pred = test_dataset.task.colorize(pred2, big_orig)
                imutil.imwrite(new_blend_fpath, big_blend_instance_pred)

        mode = 'pred_crf'
        mode = 'pred'
        restitched_paths = pharn._restitch_type(mode, blend='vote')

        big_pred_fpath = restitched_paths[17]
        orig_fname = basename(big_pred_fpath).replace('.png', '_RGB.tif')
        big_orig_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', orig_fname)
        # big_orig_fpath = '/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/TAM_Tile_017_RGB.tif'

        big_pred = imutil.imread(big_pred_fpath)
        big_orig = imutil.imread(big_orig_fpath)

        k = 3
        kernel = np.ones((k, k), np.uint8)
        import cv2
        opening = cv2.morphologyEx(big_pred, cv2.MORPH_OPEN, kernel, iterations=2)
        n_ccs, cc_labels = cv2.connectedComponents(opening.astype(np.uint8), connectivity=4)

        # cc_labels = task.instance_label(big_pred)

        big_blend_instance_pred = test_dataset.task.instance_colorize(cc_labels, big_orig)
        # big_blend_instance_pred = task.colorize(cc_labels > 0, big_orig)
        restitched_pred_dpath = ub.ensuredir((pharn.test_dump_dpath, 'restiched', 'blend_instance_' + mode))
        fname = basename(big_pred_fpath)
        imutil.imwrite(join(restitched_pred_dpath, fname), big_blend_instance_pred)

    if 1:
        import pandas as pd  # NOQA
        from .metrics import confusion_matrix, jaccard_score_from_confusion  # NOQA
        from .torch import filters  # NOQA

        paths = {}
        for mode in ['pred', 'pred_crf']:
            restitched_paths = pharn._restitch_type(mode, blend='vote')
            paths[mode] = restitched_paths

        scores = {}
        import cv2
        for mode in ['pred', 'pred_crf']:
            print('mode = {!r}'.format(mode))
            restitched_paths = paths[mode]

            for n_iters in range(1, 2):
                for k in range(5, 10, 2):
                    for watershed in [False, True]:
                        cfsn2 = np.zeros((3, 3))
                        for big_pred_fpath in restitched_paths:
                            big_pred = imutil.imread(big_pred_fpath)

                            big_gt_fname = basename(big_pred_fpath).replace('.png', '_GTL.tif')
                            big_gt_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', big_gt_fname)
                            big_gt = imutil.imread(big_gt_fpath)
                            big_gt[big_gt == 2] = 0
                            big_gt[big_gt == 6] = 1
                            big_gt[big_gt == 65] = 2

                            pred2 = (test_dataset.task.instance_label(
                                big_pred, k=k, n_iters=n_iters,
                                watershed=watershed) > 0).astype(np.int8)

                            # # cfsn1 += confusion_matrix(big_gt.ravel(), big_pred.ravel(), labels=[0, 1, 2])
                            # if k > 0:
                            #     kernel = np.ones((k, k), np.uint8)
                            #     opening = cv2.morphologyEx(big_pred, cv2.MORPH_OPEN, kernel, iterations=n_iters)
                            #     # opening = filters.watershed_filter(opening)
                            #     # n_ccs, cc_labels = cv2.connectedComponents(opening.astype(np.uint8), connectivity=4)
                            #     # pred2 = (cc_labels > 0).astype(np.int)
                            #     pred2 = opening
                            # else:
                            #     pred2 = big_pred

                            cfsn2 += confusion_matrix(big_gt.ravel(), pred2.ravel(), labels=[0, 1, 2])

                        miou = jaccard_score_from_confusion(cfsn2)[0:2].mean()
                        scores[(mode, k, n_iters, watershed)] = miou
                        print('mode={}, k={:3d}, n_iters={}, w={} miou = {!r}'.format(mode, k, n_iters, int(watershed), miou))

        print(pd.Series(scores).sort_values())


class PredictHarness(object):
    def __init__(pharn, dataset):
        pharn.dataset = dataset
        pharn.xpu = xpu_device.XPU.from_argv()
        pharn.model = None
        pharn.test_dump_dpath = None

    def load_snapshot(pharn, load_path):
        print('Loading snapshot onto {}'.format(pharn.xpu))
        snapshot = torch.load(load_path, map_location=pharn.xpu.map_location())

        if 'model_kw' not in snapshot:
            # FIXME: we should be able to get information from the snapshot
            print('warning snapshot not saved with modelkw')
            n_classes = pharn.dataset.n_classes
            n_channels = pharn.dataset.n_channels

        # Infer which model this belongs to
        if snapshot['model_class_name'] == 'UNet':
            pharn.model = models.UNet(in_channels=n_channels, n_classes=n_classes)
        elif snapshot['model_class_name'] == 'SegNet':
            pharn.model = models.SegNet(in_channels=n_channels, n_classes=n_classes)

        pharn.model = pharn.xpu.to_xpu(pharn.model)
        pharn.model.load_state_dict(snapshot['model_state_dict'])

    def hack_dump_path(pharn, load_path):
        # HACK
        eval_dpath = ub.ensuredir((pharn.dataset.task.workdir, pharn.dataset.tag, 'input_' + pharn.dataset.input_id))
        subdir = list(ub.take(os.path.splitext(load_path)[0].split('/'), [-3, -1]))
        # base output dump path on the training id string
        pharn.test_dump_dpath = ub.ensuredir((eval_dpath, '/'.join(subdir)))
        print('pharn.test_dump_dpath = {!r}'.format(pharn.test_dump_dpath))

    def _restitch_type(pharn, mode, blend='vote'):
        """
        hacky camvid-only code to restitch parts into a whole segmentation
        """
        mode_paths = sorted(glob.glob(pharn.test_dump_dpath + '/{}/*.png'.format(mode)))
        restitched_mode_dpath = ub.ensuredir((pharn.test_dump_dpath, 'restiched', mode))
        restitched_mode = pharn.dataset.task.restitch(restitched_mode_dpath, mode_paths, blend=blend)
        return restitched_mode

    def run(pharn):
        print('Preparing to predict {} on {}'.format(pharn.model.__class__.__name__, pharn.xpu))
        pharn.model.train(False)

        for ix in ub.ProgIter(range(len(pharn.dataset)), label='dumping'):
            inputs_ = pharn.dataset[ix][None, :]

            inputs_ = pharn.xpu.to_xpu(inputs_)
            inputs_ = torch.autograd.Variable(inputs_)

            output_tensor = pharn.model(inputs_)
            log_prob_tensor = torch.nn.functional.log_softmax(output_tensor, dim=1)[0]
            log_probs = log_prob_tensor.data.cpu().numpy()

            # Just reload rgb data without trying to go through the reverse
            # transform
            img = imutil.imread(pharn.dataset.inputs.im_paths[ix])

            # ut.save_cPkl('crf_testdata.pkl', {
            #     'log_probs': log_probs,
            #     'img': img,
            # })

            from clab.torch import filters

            posterior = filters.crf_posterior(img, log_probs)
            # output = prob_tensor.data.cpu().numpy()[0]

            pred = log_probs.argmax(axis=0)
            pred_crf = posterior.argmax(axis=0)

            fname = pharn.dataset.inputs.dump_im_names[ix]
            fname = os.path.splitext(fname)[0] + '.png'

            # pred = argmax.data.cpu().numpy()[0]
            blend_pred = pharn.dataset.task.colorize(pred, img)
            blend_pred_crf = pharn.dataset.task.colorize(pred_crf, img)
            # color_pred = task.colorize(pred)

            output_dict = {
                'log_probs': log_probs,
                'blend_pred': blend_pred,
                # 'color_pred': color_pred,
                'blend_pred_crf': blend_pred_crf,
                'pred_crf': pred_crf,
                'pred': pred,
            }

            if pharn.dataset.with_gt:
                true = imutil.imread(pharn.dataset.inputs.gt_paths[ix])
                blend_true = pharn.dataset.task.colorize(true, img, alpha=.5)
                # color_true = task.colorize(true, alpha=.5)
                output_dict['true'] = true
                output_dict['blend_true'] = blend_true
                # output_dict['color_true'] = color_true

            for key, img in output_dict.items():
                dpath = join(pharn.test_dump_dpath, key)
                ub.ensuredir(dpath)
                fpath = join(dpath, fname)
                if key == 'log_probs':
                    np.savez(fpath.replace('.png', ''), img)
                else:
                    imutil.imwrite(fpath, img)


def instance_fscore(gti, uncertain, dsm, pred):
    """
    path = '/home/local/KHQ/jon.crall/data/work/urban_mapper/eval/input_4224-rwyxarza/solver_4214-yxalqwdk_unet_vgg_nttxoagf_a=1,n_ch=5,n_cl=3/_epoch_00000236/restiched/pred'
    mode_paths = sorted(glob.glob(path + '/*.png'))



    for k in [3, 5, 7, 9, 11, 13, 14, 15, 16]:
        # for d in [3, 4, 5, 6, 7, 8]:
        for n in [1, 2, 3]:

            fscores = []
            for pred_fpath in ub.ProgIter(mode_paths):
                gtl_fname = basename(pred_fpath).replace('.png', '_GTL.tif')
                gti_fname = basename(pred_fpath).replace('.png', '_GTI.tif')
                dsm_fname = basename(pred_fpath).replace('.png', '_DSM.tif')
                gtl_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', gtl_fname)
                gti_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', gti_fname)
                dsm_fpath = join('/home/local/KHQ/jon.crall/remote/aretha/data/UrbanMapper3D/training/', dsm_fname)

                from clab.tasks.urban_mapper_3d import UrbanMapper3D
                task = UrbanMapper3D('', '')

                pred = task.instance_label(util.imread(pred_fpath), dist_thresh=d, k=k, watershed=True)
                gti = util.imread(gti_fpath)
                gtl = util.imread(gtl_fpath)
                dsm = util.imread(dsm_fpath)

                uncertain = (gtl == 65)

                fscore = instance_fscore(gti, uncertain, dsm, pred)
                fscores.append(fscore)
            print('k = {!r}'.format(k))
            print('d = {!r}'.format(d))
            print(np.mean(fscores))


    from .torch import profiler
    instance_fscore_ = dynamic_profile(instance_fscore)
    fscore = instance_fscore_(gti, uncertain, dsm, pred)
    instance_fscore_.profile.profile.print_stats()
    """
    gti_rc = np.where(gti)
    gti_rc_arr = np.ascontiguousarray(np.vstack(gti_rc).T)
    gti_label = gti[gti_rc]

    pred_rc = np.where(pred)
    pred_label = pred[pred_rc]
    pred_rc_arr = np.ascontiguousarray(np.vstack(pred_rc).T)

    import vtool as vt
    group_true_labels, true_groupxs = vt.group_indices(gti_label)
    grouped_true_rc_arrs = vt.apply_grouping(gti_rc_arr, true_groupxs, axis=0)

    group_pred_labels, pred_groupxs = vt.group_indices(pred_label)
    grouped_pred_rc_arrs = vt.apply_grouping(pred_rc_arr, pred_groupxs, axis=0)

    # true_rcs_arr = ub.map_vals(np.array, ub.group_items(np.vstack(gti_rc).T, gti_label))
    # true_rcs = ub.map_vals(lambda x: set(map(tuple, x)), true_rcs_arr)

    # Find uncertain truth
    uncertain_labels = set(np.unique(gti[uncertain.astype(np.bool)]))
    for ix, (label, rc_arr) in enumerate(zip(group_true_labels, grouped_true_rc_arrs)):
        if len(rc_arr) < 100:
            rc_arr = np.array(list(rc_arr))
            if (np.any(rc_arr == 0) or np.any(rc_arr == 2047)):
                uncertain_labels.add(label)
            else:
                rc_loc = tuple(rc_arr.T)
                is_invisible = (dsm[rc_loc] == -32767)
                if np.any(is_invisible):
                    print('is_invisible = {!r}'.format(is_invisible))
                    invisible_rc = rc_arr.compress(is_invisible, axis=0)
                    invisible_rc_set = set(map(tuple, invisible_rc))
                    # Remove invisible pixels
                    remain_rc_set = list(set(map(tuple, rc_arr)).difference(invisible_rc_set))
                    grouped_true_rc_arrs[ix] = np.array(remain_rc_set)
                    uncertain_labels.add(label)

    # using nums instead of tuples gives the intersection a modest speedup
    pred_rc_int = pred_rc_arr.T[0] + pred.shape[0] + pred_rc_arr.T[1]
    true_rc_int = gti_rc_arr.T[0] + pred.shape[0] + gti_rc_arr.T[1]
    true_rcs_ = dict(zip(group_true_labels, map(set, vt.apply_grouping(true_rc_int, true_groupxs))))
    pred_rcs_ = dict(zip(group_pred_labels, map(set, vt.apply_grouping(pred_rc_int, pred_groupxs))))

    # true_rcs_ = ub.map_vals(set, true_rcs_)
    # pred_rcs_ = ub.map_vals(set, pred_rcs_)

    true_rcs_arr = dict(zip(group_true_labels, grouped_true_rc_arrs))
    pred_rcs_arr = dict(zip(group_pred_labels, grouped_pred_rc_arrs))

    # pred_rcs_arr = ub.map_vals(np.array, ub.group_items(np.vstack(pred_rc).T, pred_label))
    # pred_rcs = ub.map_vals(lambda x: set(map(tuple, x)), pred_rcs_arr)

    # true_rcs_ = ub.map_vals(lambda x: np.array(sorted([r * pred.shape[0] + c for (r, c) in x])), true_rcs)
    # pred_rcs_ = ub.map_vals(lambda x: np.array(sorted([r * pred.shape[0] + c for (r, c) in x])), pred_rcs)

    # using nums instead of tuples gives the intersection a modest speedup
    # true_rcs_ = ub.map_vals(lambda x: {r * pred.shape[0] + c for (r, c) in x}, true_rcs)
    # pred_rcs_ = ub.map_vals(lambda x: {r * pred.shape[0] + c for (r, c) in x}, pred_rcs)
    # true_rcs_ = true_rcs.copy()
    # pred_rcs_ = pred_rcs.copy()

    # Make intersection a bit faster by filtering via bbox fist
    def _bbox(arr):
        r1, c1 = arr.min(axis=0)
        r2, c2 = arr.max(axis=0)
        return np.array([r1, c1, r2, c2])

    def _bbox_isect_area(bbox1, bbox2):
        i2 = np.minimum(bbox1[2:4], bbox2[2:4])
        i1 = np.minimum(np.maximum(bbox1[0:2], bbox2[0:2]), i2)
        return np.prod(i2 - i1)

    true_rcs_bbox = ub.map_vals(_bbox, true_rcs_arr)
    pred_rcs_bbox = ub.map_vals(_bbox, pred_rcs_arr)

    # Greedy matching
    unused_true_rcs = true_rcs_.copy()
    FP = TP = FN = 0
    unused_true_keys = sorted(unused_true_rcs.keys())
    for pred_label, pred_rc_set in sorted(pred_rcs_.items()):

        best_score = (-np.inf, -np.inf)
        best_label = None

        bbox1 = pred_rcs_bbox[pred_label]

        for true_label in unused_true_keys:
            bbox2 = true_rcs_bbox[true_label]

            # Try and short circuit the intersection code
            if _bbox_isect_area(bbox1, bbox2) > 0:
                true_rc_set = unused_true_rcs[true_label]

                n_isect = len(pred_rc_set.intersection(true_rc_set))
                # n_isect = len(np.intersect1d(pred_rc_set, true_rc_set, assume_unique=True))
                iou = n_isect / (len(true_rc_set) + len(pred_rc_set) - n_isect)
                if iou > .45:
                    score = (iou, -len(true_rc_set))
                    if score > best_score:
                        best_score = score
                        best_label = true_label

        if best_label is not None:
            unused_true_keys.remove(best_label)
            if pred_label not in uncertain_labels:
                TP += 1
        else:
            FP += 1

    FN += len(unused_true_rcs)

    precision = TP / (TP + FP)
    recall = TP / (TP + FN)
    f_score = 2 * precision * recall / (precision + recall)

    # They multiply by 1e6, but lets not do that.
    return f_score