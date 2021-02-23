r'''
Adaption to act as the MLP layer using an MoE MLP layer in transformer.
'''
import torch
import torch.nn as nn
from .gates import NaiveGate
from .layers import FMoE, FMoELinear


class _Expert(nn.Module):
    r'''
    An expert using 2 FMoELinear modules to speed up the computation of experts
    within one worker.
    '''
    def __init__(self, num_expert, d_model, d_hidden, activation, rank=0):
        super().__init__()
        self.htoh4 = FMoELinear(num_expert, d_model, d_hidden,
                bias=True, rank=rank)
        self.h4toh = FMoELinear(num_expert, d_hidden, d_model,
                bias=True, rank=rank)
        self.activation = activation

    def forward(self, inp, fwd_expert_count):
        r'''
        First expand input to 4h (the hidden size is variable, but is called h4
        for convenience). Then perform activation. Finally shirink back to h.
        '''
        x = self.htoh4(inp, fwd_expert_count)
        x = self.activation(x)
        x = self.h4toh(x, fwd_expert_count)
        return x


class FMoETransformerMLP(FMoE):
    r'''
    A complete MoE MLP module in a Transformer block.
    * `activation` is the activation function to be used in MLP in each expert.
    * `d_hidden` is the dimension of the MLP layer.
    '''
    def __init__(
        self,
        num_expert=32,
        d_model=1024,
        d_hidden=4096,
        world_size=1,
        mp_group=None,
        activation=torch.nn.functional.gelu,
        gate=NaiveGate,
        top_k=2,
        do_lnorm=False,
        pre_lnorm=False,
        expert_dp_comm='none'
    ):
        super().__init__(num_expert=num_expert, d_model=d_model, gate=gate,
                top_k=top_k, world_size=world_size, mp_group=mp_group)
        self.experts = _Expert(num_expert, d_model, d_hidden, activation,
                rank=self.mp_rank)
        self.pre_lnorm = pre_lnorm
        if do_lnorm:
            self.layer_norm = nn.LayerNorm(d_model)
            self.pre_lnorm = pre_lnorm
        else:
            self.pre_lnorm = None
        self.mark_parallel_comm(expert_dp_comm)

    def forward(self, inp: torch.Tensor):
        r'''
        This module wraps up the FMoE module with reshape, residual and layer
        normalization.
        '''
        original_shape = inp.shape
        inp = inp.reshape(-1, self.d_model)
        if self.pre_lnorm is not None and self.pre_lnorm:
            inp = self.layer_norm(inp)
        output = super().forward(inp) + inp
        if self.pre_lnorm is not None and not self.pre_lnorm:
            output = self.layer_norm(output)
        return output.reshape(original_shape)
