def get_text(result, task=None) -> str:
    """Same idea as Leo: task.output.raw, or str(result) as a backup."""
    try:
        if task is not None and task.output is not None and getattr(task.output, "raw", None):
            return task.output.raw
    except Exception:
        pass
    return str(result)
