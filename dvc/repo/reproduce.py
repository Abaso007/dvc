import logging
from typing import TYPE_CHECKING, List, Optional, cast

from funcy import ldistinct

from dvc.exceptions import ReproductionError
from dvc.repo.scm_context import scm_context
from dvc.stage.cache import RunCacheNotSupported

from . import locked

if TYPE_CHECKING:
    from networkx import DiGraph

    from dvc.stage import Stage

    from . import Repo

logger = logging.getLogger(__name__)


def _reproduce_stage(stage: "Stage", **kwargs) -> Optional["Stage"]:
    if stage.frozen and not stage.is_import:
        logger.warning(
            "%s is frozen. Its dependencies are not going to be reproduced.",
            stage,
        )

    ret = stage.reproduce(**kwargs)
    if ret and not kwargs.get("dry", False):
        stage.dump(update_pipeline=False)
    return ret


@locked
@scm_context
def reproduce(  # noqa: C901, PLR0912
    self: "Repo",
    targets=None,
    recursive=False,
    pipeline=False,
    all_pipelines=False,
    **kwargs,
):
    from .graph import get_pipeline, get_pipelines

    glob = kwargs.pop("glob", False)

    if isinstance(targets, str):
        targets = [targets]

    if not all_pipelines and not targets:
        from dvc.dvcfile import PROJECT_FILE

        targets = [PROJECT_FILE]

    targets = targets or []
    interactive = kwargs.get("interactive", False)
    if not interactive:
        kwargs["interactive"] = self.config["core"].get("interactive", False)

    stages = []
    if pipeline or all_pipelines:
        pipelines = get_pipelines(self.index.graph)
        if all_pipelines:
            used_pipelines = pipelines
        else:
            used_pipelines = []
            for target in targets:
                stage = self.stage.get_target(target)
                used_pipelines.append(get_pipeline(pipelines, stage))

        for pline in used_pipelines:
            for stage in pline:
                if pline.in_degree(stage) == 0:
                    stages.append(stage)
    else:
        for target in targets:
            stages.extend(
                self.stage.collect(
                    target,
                    recursive=recursive,
                    glob=glob,
                )
            )

    if kwargs.get("pull", False) and kwargs.get("run_cache", True):
        logger.debug("Pulling run cache")
        try:
            self.stage_cache.pull(None)
        except RunCacheNotSupported as e:
            logger.warning("Failed to pull run cache: %s", e)

    return _reproduce_stages(self.index.graph, ldistinct(stages), **kwargs)


def _reproduce_stages(  # noqa: C901
    graph: "DiGraph",
    stages: List["Stage"],
    force_downstream: bool = False,
    downstream: bool = False,
    single_item: bool = False,
    **kwargs,
) -> List["Stage"]:
    r"""Derive the evaluation of the given node for the given graph.

    When you _reproduce a stage_, you want to _evaluate the descendants_
    to know if it make sense to _recompute_ it. A post-ordered search
    will give us an order list of the nodes we want.

    For example, let's say that we have the following pipeline:

                               E
                              / \
                             D   F
                            / \   \
                           B   C   G
                            \ /
                             A

    The derived evaluation of D would be: [A, B, C, D]

    In case that `downstream` option is specified, the desired effect
    is to derive the evaluation starting from the given stage up to the
    ancestors. However, the `networkx.ancestors` returns a set, without
    any guarantee of any order, so we are going to reverse the graph and
    use a reverse post-ordered search using the given stage as a starting
    point.

                   E                                   A
                  / \                                 / \
                 D   F                               B   C   G
                / \   \        --- reverse -->        \ /   /
               B   C   G                               D   F
                \ /                                     \ /
                 A                                       E

    The derived evaluation of _downstream_ B would be: [B, D, E]
    """
    from .graph import get_steps

    if not single_item:
        active = _remove_frozen_stages(graph)
        stages = get_steps(active, stages, downstream=downstream)

    result: List["Stage"] = []
    for i, stage in enumerate(stages):
        try:
            ret = _reproduce_stage(stage, upstream=stages[:i], **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise ReproductionError(stage.addressing) from exc

        if not ret:
            continue

        result.append(ret)
        if force_downstream:
            # NOTE: we are walking our pipeline from the top to the
            # bottom. If one stage is changed, it will be reproduced,
            # which tells us that we should force reproducing all of
            # the other stages down below, even if their direct
            # dependencies didn't change.
            kwargs["force"] = True
        if i < len(stages) - 1:
            logger.info("")  # add a newline
    return result


def _remove_frozen_stages(graph: "DiGraph") -> "DiGraph":
    g = cast("DiGraph", graph.copy())
    for stage in graph:
        if stage.frozen:
            # NOTE: disconnect frozen stage from its dependencies
            g.remove_edges_from(graph.out_edges(stage))
    return g
