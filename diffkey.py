from henry import constants
import sys

with open(sys.argv[1]) as f:
    keys = set(f.read().split())
real_keys = set(dir(constants))

for x in keys - real_keys:
    print(x)
