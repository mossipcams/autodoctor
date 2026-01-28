# Allowed Commands

Commands Claude can run without permission prompts in this project.

## Testing

```
pytest
pytest tests/
pytest tests/test_*.py
pytest -v
pytest -x
pytest --tb=short
pytest -k <pattern>
```

## Type Checking

```
mypy custom_components/autodoctor
mypy .
```

## Linting & Formatting

```
ruff check .
ruff check custom_components/autodoctor
ruff format --check .
ruff format .
black --check .
black .
isort --check .
isort .
```

## Git (Read-Only)

```
git status
git diff
git diff --cached
git log
git log --oneline
git log -n <number>
git branch
git branch -a
git show
git blame <file>
git -C <path> status
git -C <path> log
git -C <path> log --oneline
git -C <path> diff
```

## Project Info

```
ls
ls -la
tree
cat pyproject.toml
cat manifest.json
python --version
pip list
pip show <package>
```

## Virtual Environment

```
source venv/bin/activate
which python
which pytest
```
