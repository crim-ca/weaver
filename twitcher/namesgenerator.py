"""
generates a nice birdy name.

This module is inspired by
`docker names-generator.go <https://github.com/docker/docker/blob/master/pkg/namesgenerator/names-generator.go>`_
"""

import random
import re

left = ["admiring",
        "adoring",
        "agitated",
        "amazing",
        "angry",
        "awesome",
        "backstabbing",
        "berserk",
        "big",
        "blind",
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
        "running",
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

# pick a nice bird: https://en.wikipedia.org/wiki/List_of_birds_by_common_name

right = [
    "albatrosse",
    "antbird",
    "buzzard",
    "cassowary",
    "catbird",
    "chicken",
    "crane",
    "cuckoo",

    # dodrio: http://bulbapedia.bulbagarden.net/wiki/Dodrio_%28Pok%C3%A9mon%29
    "dodrio",

    "dove",
    "duck",
    "eagle",
    "emu",
    "figbird",
    "flamingo",
    "flycatcher",
    "goldfinch",
    "goose",
    "grouse",
    "hawk",
    "honeyeater",
    "hornbill",
    "hummingbird",
    "ibis",
    "kingfisher",
    "kiwi",
    "leafbird",
    "lovebird",
    "malleefowl",
    "mockingbird",
    "mousebird",
    "nightjar",
    "ostriche",
    "owl",
    "parrot",
    "pelican",
    "penguin",
    "pheasant",
    "pigeon",
    "roadrunner",
    "satinbird",
    "seagull",
    "snowfinch",
    "sparrow",
    "starling",
    "stork",
    "sugarbird",
    "sunbird",
    "swan",
    "swift",
    "tinamou",
    "toucan",
    "trogon",
    "turaco",
    "turkey",
    "woodcreeper",
    "woodpecker",
]


def get_random_name(retry=False):
    """
    generates a random name from the list of adjectives and birds in this package
    formatted as "adjective_surname". For example 'loving_sugarbird'. If retry is non-zero, a random
    integer between 0 and 100 will be added to the end of the name, e.g `loving_sugarbird3`
    """
    name = "%s_%s" % (left[random.randint(0, len(left) - 1)], right[random.randint(0, len(right) - 1)])
    if retry is True:
        name = "%s%d" % (name, random.randint(0, 100))
    return name


def get_sane_name(name, minlen=3, maxlen=25):
    if name is None or len(name.strip()) < minlen:
        return None
    return re.sub("[^a-z]", "_", name.strip().lower()[:maxlen])
