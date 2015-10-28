"""
generates a nice birdy name.

This module is inspired by
`docker names-generator.go <https://github.com/docker/docker/blob/master/pkg/namesgenerator/names-generator.go>`_
"""

import random

left = ["admiring",
        "adoring",
        "agitated",
        "amazing",
        "angry",
        "awesome",
        "backstabbing",
        "berserk",
        "big",
        "boring",
        "clever",
        "cocky",
        "compassionate",
        "condescending",
        "cranky",
        "desperate",
        "determined",
        "distracted",
        "dreamy",
        "drunk",
        "ecstatic",
        "elated",
        "elegant",
        "evil",
        "fervent",
        "focused",
        "furious",
        "gigantic",
        "gloomy",
        "goofy",
        "grave",
        "happy",
        "high",
        "hopeful",
        "hungry",
        "insane",
        "jolly",
        "jovial",
        "kickass",
        "lonely",
        "loving",
        "mad",
        "modest",
        "naughty",
        "nostalgic",
        "pensive",
        "prickly",
        "reverent",
        "romantic",
        "sad",
        "serene",
        "sharp",
        "sick",
        "silly",
        "sleepy",
        "small",
        "stoic",
        "stupefied",
        "suspicious",
        "tender",
        "thirsty",
        "tiny",
        "trusting",
        ]


right = [
        "albattani",
        "allen",
        "almeida",
        "archimedes",
        "jang",
        ]

def get_random_name(retry=False):
    """
    GetRandomName generates a random name from the list of adjectives and surnames in this package
    formatted as "adjective_surname". For example 'focused_turing'. If retry is non-zero, a random
    integer between 0 and 10 will be added to the end of the name, e.g `focused_turing3`
    """
    name = "%s_%s" % ( left[random.randint(0, len(left)-1)], right[random.randint(0, len(right)-1)] )
    if retry:
        name = "%s%d" % (name, random.randint(1,10))
    return name

