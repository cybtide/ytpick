"""ytpick: YouTube durchsuchen, Videos auswählen und in bester Qualität laden."""

__version__ = "0.5.0"


def main(argv=None):
    from .app import main as run
    return run(argv)
