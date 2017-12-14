from os.path import join
import ubelt as ub
from clab import util


class DirectoryStructure(object):
    def __init__(self, workdir='.', hyper=None, datasets=None,
                 pretrained=None):
        self.datasets = datasets
        self.workdir = workdir
        self.hyper = hyper

    def make_dpath(self):
        train_hyper_id = self.hyper.hyper_id()
        suffix = '_' + self.hyper.other_id()

    def write_train_info():
        # TODO: if pretrained is another clab model, then we should read that
        # train_info if it exists and append it to a running list of train_info
        train_info =  {
            'arch': arch,
            'train_id': datasets['train'].input_id,
            'train_hyper_id': train_hyper_id,
            'train_hyper_hashid': train_hyper_hashid,
            'colorspace': datasets['train'].colorspace,
        }


def make_training_dpath(workdir, arch, datasets, hyper,
                        pretrained=None,
                        train_hyper_id=None, suffix=''):
    """
    from clab.torch.sseg_train import *
    datasets = load_task_dataset('urban_mapper_3d')
    datasets['train']._make_normalizer()
    arch = 'foobar'
    workdir = datasets['train'].task.workdir
    ut.exec_funckw(directory_structure, globals())
    """
    # workdir = os.path.expanduser('~/data/work/pycamvid')
    arch_dpath = ub.ensuredir((workdir, 'arch', arch))
    train_base = ub.ensuredir((arch_dpath, 'train'))
    test_base = ub.ensuredir((arch_dpath, 'test'))
    test_dpath = ub.ensuredir((test_base, 'input_' + datasets['test'].input_id))

    train_init_id = pretrained
    train_hyper_hashid = util.hash_data(train_hyper_id)[:8]

    train_id = '{}_{}_{}_{}'.format(
        datasets['train'].input_id, arch, train_init_id, train_hyper_hashid) + suffix

    train_dpath = ub.ensuredir((
        train_base,
        'input_' + datasets['train'].input_id, 'solver_{}'.format(train_id)
    ))

    train_info =  {
        'arch': arch,
        'train_id': datasets['train'].input_id,
        'train_hyper_id': train_hyper_id,
        'train_hyper_hashid': train_hyper_hashid,
        'colorspace': datasets['train'].colorspace,
    }
    if hasattr(datasets['train'], 'center_inputs'):
        # Hack in centering information
        # TODO: better serialization
        train_info['hack_centers'] = [
            (t.__class__.__name__, t.__getstate__())
            # ub.map_vals(str, t.__dict__)
            for t in datasets['train'].center_inputs.transforms
        ]
    util.write_json(join(train_dpath, 'train_info.json'), train_info)

    print('+=========')
    # print('hyper_strid = {!r}'.format(params.hyper_id()))
    print('train_init_id = {!r}'.format(train_init_id))
    print('arch = {!r}'.format(arch))
    print('train_hyper_hashid = {!r}'.format(train_hyper_hashid))
    print('train_hyper_id = {!r}'.format(train_hyper_id))
    print('train_id = {!r}'.format(train_id))
    print('+=========')

    return train_dpath, test_dpath
