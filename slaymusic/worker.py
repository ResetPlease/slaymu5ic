import math
import os
import resource
import sys


def main():
    memory_mb, timeout, executable, *args = sys.argv[1:]
    if sys.platform.startswith("linux"):
        memory = int(memory_mb) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    cpu = math.ceil(float(timeout)) + 2
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    os.execvp(executable, [executable, *args])


if __name__ == "__main__":
    main()
