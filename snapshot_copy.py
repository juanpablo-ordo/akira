"""Detach data snapshots without dispatching deepcopy for every scalar.

The input is an acyclic presentation tree, never execution objects. Keep a
deepcopy fallback for non-JSON values so this doesn't change their semantics.
"""
from copy import deepcopy


def snapshot_copy(value):
    kind=type(value)
    if kind is dict:return {key:snapshot_copy(item) for key,item in value.items()}
    if kind is list:return [snapshot_copy(item) for item in value]
    if kind is tuple:return tuple(snapshot_copy(item) for item in value)
    if kind in (str,int,float,bool,type(None)):return value
    return deepcopy(value)
