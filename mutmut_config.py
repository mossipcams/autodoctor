def pre_mutation(context):
    """Skip mutations on logging lines to reduce noise."""
    line = context.current_source_line.strip()
    if line.startswith(("_LOGGER.", "logging.")):
        context.skip = True
