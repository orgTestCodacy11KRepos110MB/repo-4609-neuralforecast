# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/models_nbeats__ensemble.ipynb (unless otherwise specified).

__all__ = ['Yearly', 'Quarterly', 'Monthly', 'common_grid', 'lookbacks', 'ensemble_grid', 'print_models_list',
           'create_loaders_M4', 'NBEATS_instantiate', 'show_tensorboard', 'NBEATSEnsemble']

# Cell
from dataclasses import dataclass
from itertools import product
from pathlib import Path
import shutil
from typing import Callable, Dict, Iterable, Union, List
from tqdm import tqdm
import pylab as plt
from pylab import rcParams
import math
from IPython.display import clear_output
import torch
import numpy as np
import pandas as pd
import pytorch_lightning as pl
from pytorch_lightning.loggers import TensorBoardLogger

from .nbeats import NBEATS
from ...data.datasets.m4 import M4Info, M4, M4Evaluation
from ...data.tsdataset import WindowsDataset
from ...data.tsloader import TimeSeriesLoader
from ...experiments.utils import create_datasets, get_mask_dfs

# Cell
def _parameter_grid(grid):
    specs_list = list(product(*list(grid.values())))
    model_specs_df = pd.DataFrame(specs_list, columns=list(grid.keys()))

    return model_specs_df

# Cell
common_grid = {}

# Architecture parameters
common_grid['activation'] = ['ReLU'] # Oreshkin
common_grid['n_x'] = [0] # No exogenous variables
common_grid['n_s'] = [0] # No static variables
common_grid['n_x_hidden'] = [0] # No exogenous variables
common_grid['n_s_hidden'] = [0] # No static variables
common_grid['stack_types'] = [['trend', 'seasonality']] # NBEATS-I original architecture
common_grid['n_blocks'] = [[3, 3]] # Trend blocks, Seasonal blocks - Oreshkin
common_grid['n_layers'] = [[4, 4]] # Trend-block layers, Seasonal-block - Oreshkin
common_grid['shared_weights'] = [True] # Oreshkin
common_grid['n_harmonics'] = [1] # Oreshkin
common_grid['n_polynomials'] = [2] # Trend polynomial degree
common_grid['n_theta_hidden'] = [[common_grid['n_layers'][0][0] * [256],
                                  common_grid['n_layers'][0][1] * [2048]]] # Oreshkin
common_grid['initialization'] = ['lecun_normal'] # Arbitrary

# Optimization parameters
common_grid['learning_rate'] = [0.001] # Oreshkin
common_grid['lr_decay'] = [0] # No lr_decay in the original implementation
common_grid['lr_decay_step_size'] = [1_000] # No lr_decay in the original implementation
common_grid['loss_val'] = ['SMAPE']
common_grid['dropout_prob_theta'] = [0] # No dropout in the original implementation
common_grid['weight_decay'] = [0] # # No weight_decay in the original implementation
common_grid['batch_size'] = [1024] # Oreshkin
common_grid['batch_normalization'] = [False] # No batch_normalization in the original implementation

# Data Parameters
common_grid['complete_inputs'] = [False] # ???
common_grid['mode'] = ['simple'] # ???
lookbacks = list(range(2, 8)) # Change to range(2, 8). Oreshkin

ensemble_grid = {'loss_train': ['MAPE', 'SMAPE', 'MASE'],
                #  'loss_train': ['MAPE', 'SMAPE', 'MASE'],
                 'n_steps': [260],
                 'random_seed': list(range(1))}

@dataclass
class Yearly:
    group = M4Info['Yearly']

    grid_freq = {}
    grid_freq['n_time_in'] = [M4Info['Yearly'].horizon * i for i in lookbacks]
    grid_freq['n_time_out'] = [group.horizon]
    grid_freq['train_sample_freq'] = [1] # ???
    grid_freq['frequency'] = ['Y'] # ???
    grid_freq['seasonality'] = [1] # ???
    grid_freq['l_h'] = [1.5] # Oreshkin

    grid = {**common_grid,
            **grid_freq}
    ensemble_grid = ensemble_grid

@dataclass
class Quarterly:
    group = M4Info['Quarterly']

    grid_freq = {}
    grid_freq['n_time_in'] = [M4Info['Quarterly'].horizon * i for i in lookbacks]
    grid_freq['n_time_out'] = [group.horizon]
    grid_freq['train_sample_freq'] = [1] # ???
    grid_freq['frequency'] = ['Q'] # ???
    grid_freq['seasonality'] = [4] # ???
    grid_freq['l_h'] = [1.5] # Oreshkin

    grid = {**common_grid,
            **grid_freq}
    ensemble_grid = ensemble_grid

@dataclass
class Monthly:
    group = M4Info['Monthly']

    grid_freq = {}
    grid_freq['n_time_in'] = [M4Info['Monthly'].horizon * i for i in lookbacks]
    grid_freq['n_time_out'] = [group.horizon]
    grid_freq['train_sample_freq'] = [1] # ???
    grid_freq['frequency'] = ['M'] # ???
    grid_freq['seasonality'] = [12] # ???
    grid_freq['l_h'] = [1.5] # Oreshkin

    grid = {**common_grid,
            **grid_freq}
    ensemble_grid = ensemble_grid

# Cell
def print_models_list(frequencies: list, table_width: int):
    for freq in frequencies:
        freq_grid_table = pd.Series({**freq.grid, **freq.ensemble_grid})
        freq_table_header  = f'\n{freq.group.name} '
        freq_table_header += 'grid (# of different model configurations = '
        freq_table_header += f'{len(_parameter_grid({**freq.grid, **freq.ensemble_grid}))}):\n'
        print(f'{freq_table_header}{table_width*"="}\n{freq_grid_table}\n{table_width*"="}\n')

# Cell
def create_loaders_M4(Y_df, S_df, hparams, num_workers):

    print(f'Instantiating loaders (n_time_in = {hparams["n_time_in"]})...', end=' ')

    train_mask_df, valid_mask_df, _ = get_mask_dfs(Y_df=Y_df,
                                                   ds_in_test=0,
                                                   ds_in_val=hparams['n_time_out'])

    train_dataset = WindowsDataset(Y_df=Y_df, S_df=S_df,
                                   mask_df=train_mask_df,
                                   input_size=hparams['n_time_in'],
                                   output_size=hparams['n_time_out'],
                                   sample_freq=hparams['train_sample_freq'],
                                   complete_windows=hparams['complete_inputs'])

    valid_dataset = WindowsDataset(Y_df=Y_df, S_df=S_df,
                                   mask_df=valid_mask_df,
                                   input_size=hparams['n_time_in'],
                                   output_size=hparams['n_time_out'],
                                   sample_freq=hparams['train_sample_freq'],
                                   complete_windows=hparams['complete_inputs'],
                                   last_window=True)

    train_loader = TimeSeriesLoader(dataset=train_dataset,
                                    batch_size=int(hparams['batch_size']),
                                    eq_batch_size=True,
                                    num_workers=num_workers,
                                    shuffle=True)

    valid_loader = TimeSeriesLoader(dataset=valid_dataset,
                                    batch_size=int(hparams['batch_size']),
                                    eq_batch_size=False,
                                    num_workers=num_workers,
                                    shuffle=False)

    print('Data loaders ready.\n')

    del train_dataset, valid_dataset

    return train_loader, valid_loader

# Cell
def NBEATS_instantiate(hparams):

    model = NBEATS(n_time_in=int(hparams['n_time_in']),
                   n_time_out=int(hparams['n_time_out']),
                   n_x=hparams['n_x'],
                   n_s=hparams['n_s'],
                   n_s_hidden=int(hparams['n_s_hidden']),
                   n_x_hidden=int(hparams['n_x_hidden']),
                   shared_weights=hparams['shared_weights'],
                   initialization=hparams['initialization'],
                   activation=hparams['activation'],
                   stack_types=hparams['stack_types'],
                   n_blocks=hparams['n_blocks'],
                   n_layers=hparams['n_layers'],
                   n_theta_hidden=hparams['n_theta_hidden'],
                   n_harmonics=int(hparams['n_harmonics']),
                   n_polynomials=int(hparams['n_polynomials']),
                   batch_normalization = hparams['batch_normalization'],
                   dropout_prob_theta=hparams['dropout_prob_theta'],
                   learning_rate=float(hparams['learning_rate']),
                   lr_decay=float(hparams['lr_decay']),
                   lr_decay_step_size=float(hparams['lr_decay_step_size']),
                   weight_decay=hparams['weight_decay'],
                   loss_train=hparams['loss_train'],
                   loss_hypar=int(hparams['seasonality']),
                   loss_valid=hparams['loss_val'],
                   frequency=hparams['frequency'],
                   seasonality=int(hparams['seasonality']),
                   random_seed=int(hparams['random_seed']))

    return model

# Cell
def show_tensorboard(logs_path, model_path):
    logs_model_path = f'{logs_path}/{model_path}'
    # %load_ext tensorboard
    # %tensorboard --logdir $logs_model_path
    os.system('load_ext tensorboard')
    os.system('tensorboard --logdir $logs_model_path')

# Cell
class NBEATSEnsemble:

    def __init__(self, use_gpus: bool=False, gpus: int=None, auto_select_gpus: bool=False):

        if use_gpus:
            assert isinstance(gpus, (int, list, str)), \
                f'if use_gpus == True, gpus must be {int}, {list} or {str}, not {type(gpus)}.'
            if (isinstance(gpus, int)):
                assert gpus > 0 or gpus == -1, \
                    f'if gpus is of type {int}, it must be either a positive integer or equal to -1.'
        else:
            assert gpus == None, f'if use_gpus == False, gpus must be {None}, not {type(gpus)}.'

        self.gpus = gpus
        self.auto_select_gpus = auto_select_gpus

    def fit(self,
            frequencies: List[type],
            loader: callable,
            val_freq_steps: int,
            tensorboard_logs: bool,
            logs_path: str,
            num_workers: int):

        results = {}

        for freq in frequencies:
            idx_ensemble = 0

            Y_df, _, S_df = M4.load(directory='data', group=freq.group.name)
            freq_grid = _parameter_grid(freq.grid)
            forecasts = []

            if tensorboard_logs and Path(f'{logs_path}/{freq.group.name}').exists():
                shutil.rmtree(f'{logs_path}/{freq.group.name}')
                show_tensorboard(logs_path=logs_path, model_path=freq.group.name)

            for idx_hparams, row_hparams in freq_grid.iterrows():
                hparams = row_hparams.to_dict()
                train_loader, test_loader = create_loaders_M4(Y_df=Y_df,
                                                              S_df=S_df,
                                                              hparams=hparams,
                                                              num_workers=num_workers)

                ensemble_grid = _parameter_grid(freq.ensemble_grid)

                for idx_ensemble_hparams, row_ensemble_hparams in ensemble_grid.iterrows():
                    clear_output(wait=True)
                    idx_ensemble += 1
                    hparams_ensemble = {**hparams, **row_ensemble_hparams.to_dict()}

                    model = NBEATS_instantiate(hparams_ensemble)
                    self.print_model_version(freq, hparams_ensemble, idx_ensemble)

                    if tensorboard_logs: logger = self.create_logger(freq,
                                                                     hparams_ensemble,
                                                                     logs_path)
                    else: logger = False

                    trainer = pl.Trainer(max_steps=hparams_ensemble['n_steps'],
                                         gradient_clip_val=0,
                                         progress_bar_refresh_rate=50,
                                         gpus=self.gpus,
                                         auto_select_gpus=self.auto_select_gpus,
                                         check_val_every_n_epoch=val_freq_steps,
                                         logger=logger)
                    trainer.fit(model, train_dataloader=train_loader, val_dataloaders=train_loader)
                    outputs = trainer.predict(model, test_loader)

                    outputs_df = self.outputs_to_df(outputs, idx_ensemble)
                    forecasts.append(outputs_df.copy())

                    del trainer, model, outputs, outputs_df

                del train_loader, test_loader

            forecasts = pd.concat(forecasts).groupby('unique_id').median(0)
            forecasts.reset_index(inplace=True)

            results[freq.group.name] = forecasts.copy()

            del forecasts, Y_df, _, S_df

        return results

    def outputs_to_df(self, outputs, idx_ensemble):
        outputs_df = torch.vstack([outputs[i][1] \
                                   for i in range(len(outputs))]).detach().cpu().numpy()
        outputs_df = pd.DataFrame(outputs_df)
        outputs_df.insert(0, 'unique_id', np.arange(outputs_df.shape[0]))
        outputs_df.insert(1, 'model', f'm_{idx_ensemble}')

        return outputs_df

    def create_logger(self, freq, hparams, logs_path):
        name = freq.group.name
        version  = f'loss-{hparams["loss_train"]}_'
        version += f'lbl-{hparams["n_time_in"] // freq.group.horizon}_'
        version += f'_rs-{hparams["random_seed"]}'

        logger = TensorBoardLogger(logs_path, name=name, version=version, default_hp_metric=False)

        return logger

    def print_model_version(self, freq, hparams, idx_ensemble):
        n_models = len(freq.ensemble_grid['loss_train']) * \
                   len(freq.grid['n_time_in']) * \
                   len(freq.ensemble_grid['random_seed'])
        model_version  = f'\n{freq.group.name} ({idx_ensemble}/{n_models}) - '
        model_version += f'loss: {hparams["loss_train"]}, '
        model_version += f'lookback length: {hparams["n_time_in"] // freq.group.horizon}, '
        model_version += f'random_seed: {hparams["random_seed"]}'
        print(model_version)