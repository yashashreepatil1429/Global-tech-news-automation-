import logging

from scheduler import run_scheduler


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_scheduler()


if __name__ == "__main__":
    main()
