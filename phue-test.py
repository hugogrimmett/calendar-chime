# Hugo Grimmett
# October 2022
#
# pipenv install phue

from __future__ import print_function

import phue
import pdb
import time

from phue import Bridge


def main():
    print('it ran')
    b = Bridge('192.168.178.96')
    b.connect()
    # pdb.set_trace()
    b.activate_scene(1,'aoYhBTLiGLJYEYy') # meeting
    time.sleep(1)
    b.activate_scene(1,'fFTqOx3xZFwSjvu') # daytime work

    # def run_scene(self, group_name, scene_name, transition_time=4):

if __name__ == '__main__':
    main()