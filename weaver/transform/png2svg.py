"""
This module provides utilities for converting PNG images to a SVG format.

Cross-reference:
This work draws inspiration from png2svg.py, available at:
https://github.com/ianmackinnon/png2svg/blob/master/png2svg.py
"""
import operator
from collections import deque
from io import StringIO
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    from typing import List, Optional, Tuple


def add_tuple(first_tuple, second_tuple):
    # type: (Tuple[int, int], Tuple[int, int]) -> Tuple[int, int]
    return tuple(map(operator.add, first_tuple, second_tuple))


def sub_tuple(first_tuple, second_tuple):
    # type: (Tuple[int, int], Tuple[int, int]) -> Tuple[int, int]
    return tuple(map(operator.sub, first_tuple, second_tuple))


def neg_tuple(first_tuple):
    # type: (Tuple[int, int]) -> Tuple[int, int]
    return tuple(map(operator.neg, first_tuple))


def direction(edge):
    # type: (Tuple[Tuple[int, int], Tuple[int, int]]) -> Tuple[int, int]
    return sub_tuple(edge[1], edge[0])


def magnitude(tpl):
    # type: (Tuple[int, int]) -> int
    return int(pow(pow(tpl[0], 2) + pow(tpl[1], 2), .5))


def normalize(tpl):
    # type: (Tuple[int, int]) -> Tuple[int, int]
    mag = magnitude(tpl)
    assert mag > 0, "Cannot normalize a zero-length vector"
    return tuple(map(operator.truediv, tpl, [mag] * len(tpl)))


def svg_header(width, height):
    # type: (int, int) -> str
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
  "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg width="{width}" height="{height}"
     xmlns="http://www.w3.org/2000/svg" version="1.1">
"""


def joined_edges(assorted_edges, keep_every_point=False):
    # type: (List[Tuple[Tuple[int, int], Tuple[int, int]]], bool) -> List[List[Tuple[Tuple[int, int], Tuple[int, int]]]]
    pieces = []
    piece = []
    directions = deque([
        (0, 1),
        (1, 0),
        (0, -1),
        (-1, 0),
    ])
    while assorted_edges:
        if not piece:
            piece.append(assorted_edges.pop())
        current_direction = normalize(direction(piece[-1]))
        while current_direction != directions[2]:
            directions.rotate()
        for i in range(1, 4):
            next_end = add_tuple(piece[-1][1], directions[i])
            next_edge = (piece[-1][1], next_end)
            if next_edge in assorted_edges:
                assorted_edges.remove(next_edge)
                if i == 2 and not keep_every_point:
                    # same direction
                    piece[-1] = (piece[-1][0], next_edge[1])
                else:
                    piece.append(next_edge)
                if piece[0][0] == piece[-1][1]:
                    if not keep_every_point and normalize(direction(piece[0])) == normalize(direction(piece[-1])):
                        piece[-1] = (piece[-1][0], piece.pop(0)[1])
                        # same direction
                    pieces.append(piece)
                    piece = []
                break
        else:
            raise Exception("Failed to find connecting edge")
    return pieces


def rgba_image_to_svg_contiguous(img, opaque=None, keep_every_point=False):
    # type: (Image.Image, Optional[bool], bool) -> str
    # collect contiguous pixel groups

    adjacent = ((1, 0), (0, 1), (-1, 0), (0, -1))
    visited = Image.new("1", img.size, 0)

    color_pixel_lists = {}

    width, height = img.size
    for x in range(width):
        for y in range(height):
            here = (x, y)
            if visited.getpixel(here):
                continue
            rgba = img.getpixel((x, y))
            if opaque and not rgba[3]:
                continue
            piece = []
            queue = [here]
            visited.putpixel(here, 1)
            while queue:
                here = queue.pop()
                for offset in adjacent:
                    neighbour = add_tuple(here, offset)
                    if not 0 <= neighbour[0] < width or not 0 <= neighbour[1] < height:
                        continue
                    if visited.getpixel(neighbour):
                        continue
                    neighbour_rgba = img.getpixel(neighbour)
                    if neighbour_rgba != rgba:
                        continue
                    queue.append(neighbour)
                    visited.putpixel(neighbour, 1)
                piece.append(here)

            if rgba not in color_pixel_lists:
                color_pixel_lists[rgba] = []
            color_pixel_lists[rgba].append(piece)

    del adjacent
    del visited

    # calculate clockwise edges of pixel groups

    edges = {
        (-1, 0): ((0, 0), (0, 1)),
        (0, 1): ((0, 1), (1, 1)),
        (1, 0): ((1, 1), (1, 0)),
        (0, -1): ((1, 0), (0, 0)),
    }

    color_edge_lists = {}

    for rgba, pieces in color_pixel_lists.items():
        for piece_pixel_list in pieces:
            edge_set = set([])
            for coord in piece_pixel_list:
                for offset, (start_offset, end_offset) in edges.items():
                    neighbour = add_tuple(coord, offset)
                    start = add_tuple(coord, start_offset)
                    end = add_tuple(coord, end_offset)
                    edge = (start, end)
                    if neighbour in piece_pixel_list:
                        continue
                    edge_set.add(edge)
            if rgba not in color_edge_lists:
                color_edge_lists[rgba] = []
            color_edge_lists[rgba].append(edge_set)

    del color_pixel_lists
    del edges

    # join edges of pixel groups

    color_joined_pieces = {}

    for color, pieces in color_edge_lists.items():
        color_joined_pieces[color] = []
        for assorted_edges in pieces:
            color_joined_pieces[color].append(joined_edges(assorted_edges, keep_every_point))

    str = StringIO()
    str.write(svg_header(*img.size))

    for color, shapes in color_joined_pieces.items():
        for shape in shapes:
            str.write(""" <path d=" """)
            for sub_shape in shape:
                here = sub_shape.pop(0)[0]
                str.write(f" M {here[0]},{here[1]} ")
                for edge in sub_shape:
                    here = edge[0]
                    str.write(f" L {here[0]},{here[1]} ")
                str.write(" Z ")
            str.write(
                f""" " style="fill:rgb{color[0:3]}; fill-opacity:{float(color[3]) / 255:.3f}; stroke:none;" />\n""")

    str.write("""</svg>\n""")
    return str.getvalue()
