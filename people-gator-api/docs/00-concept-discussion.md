# Cluster version management and operation concepts

We always have something that uniquely identifies a cluster instance (e.g. `cluster_id`).
This is just some abstract object that covers some logical set of information units.
We need following operations on top of the clusters to have tracable and explainable cluster changes:
1. Create new cluster version based on some membership change (e.g. add/remove some information units)
2. Split a single set of information units into multiple clusters (e.g. we have a cluster with 2 different people of the same name, we want to split it into 2 clusters)
3. Merge multiple clusters into a single cluster (e.g. we have 2 clusters that actually belong to the same person, we want to merge them into a single cluster)
4. Drop a cluster (e.g. we have a cluster that is actually a false positive, we want to drop it)
5. Create parallel independent modifieable cluster versions (e.g. we want to test some algorith or there is manual annotation and do not want  to change major cluster version until we are sure about the changes)


There are main two main option of cluster management that come to mind:
1. Instance+delta based
2. Difference+modification based 

So the main difference is that we have eigher container cariiing mutability that can vbe applied as a whole. Or we have immutable states of cluster in time with chages floating arround and relationg to these points in time.


Some comments:
- Membership has always recursive definition

## point+delta based
We have a cluster **point** that has following features:
- It cannnot be modified at all, it is immutable.
- It has a unique identifier (e.g. `point_id`) that is used to refer to it.
- It has a pointer to the cluster it belongs to (e.g. `cluster_id`).
- We know what is its relation to other point/points:
    - it can be result of `union` from multiple points
    - it can be result of `intersection` from multiple points
    - it can be result of `split` from a single point
    - it can be result of `acknowledge` of a delta of previous point
    - it can be result of `parallel` independent modification of a single point

Relative to any point we can then apply some relative changes that **do not** modify it at all but rather just say *what if* we changed something about it. These changes can be:
- `add_evidence` (e.g. add some information units to the cluster point)
- `remove_evidence` (e.g. remove some information units from the cluster point)

We have one special `acknowledge` relation that acknowledges the *what if* changes and creates a new point with these changes applied. Members of the new version now include applied changes.

Initial cluster is either created `apply` as special unary operation. Or via relation to other cluster with `split` or `union` or `intersection`.

Branches are just parallel independent points linked via `parallel` relation to the same parent point. No membership change is here.

For `split` the target cluster that gets initialized. Then we create point with `split` semantic that links to the parent but is related to new cluster. We add deltas defined according to `split` to the new point and `acknowledge` the delta.

The `union` and `intersection` take members of input points and apply the respective operation. Then new point contains these members.

## Difference+modification based
For other approach. Now we have other carier called **difference** that holds modifications of cluster that can relate to any state. It has following features:
- It is mutable, it can be modified by adding new modifications to it.
- It has a unique identifier (e.g. `difference_id`) that is used to refer to it.
- It has a pointer to the cluster it belongs to (e.g. `cluster_id`).
- Any op that aims to mutate cluster then has to forever lock operand `difference` to not allow any other `modification` to be added to it.
- The following ops are defined:
   - `apply` directly mutates the previous difference chain
   - `union` a logical op that creates union of members from multiple differences.
   - `intersection` a logical op that creates intersection of members from multiple differences.
   - `parallel` a logical op that creates parallel independent difference from a single difference.
- For all ops the resulting difference can be modified until no other logical op is attached to it.
- This is done to preserve the history of changes and to have a clear lineage of how the cluster evolved over time.

The **modification** represents *actual*  change to this difference. But has same options as *delta* i.e.:
- `add_evidence` (e.g. add some information units to the cluster instance)
- `remove_evidence` (e.g. remove some information units from the cluster instance)


Now the `apply` operation adds/removes member from chain of previous differences.

The `union` and `intersection` take members of input difference chains and apply the respective operation. Then new difference contains these members.

The `split` operation creates new cluster. Then a new difference is created with `split` semantic that links to the parent but is related to new cluster. Any members tat belong to the cluster in the split are added via `add_evidence` to the new difference. Then `apply` is used to fix the original splilit and add a new modifiable head.

The `parallel` operation creates new difference with `parallel` semantic that links to the parent but is related to the same cluster. No membership change is here. But the source difference is neccesary to be locked. But other parallel differences can point to any locked difference.
