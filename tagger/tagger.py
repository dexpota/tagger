#!/usr/bin/python

from datetime import datetime

def add_track_metadata(to_tag, metadata):
    """

    :param to_tag:
    :param metadata:
    :type metadata: TrackMetadata
    :return:
    """
    to_tag.tags["TITLE"] = metadata.title
    to_tag.tags["TRACKNUMBER"] = metadata.position
    to_tag.save()

def add_album_metadata(album, files):
    """

    :param album:
    :param files:
    :type album: AlbumMetadata
    :return:
    """
    for to_tag in files:
        to_tag.tags["ARTIST"] = album.artists
        to_tag.tags["ALBUM"] = album.title
        to_tag.tags["GENRE"] = album.genres
        to_tag.tags["DATE"] = unicode(album.year)
        to_tag.tags["TRACKTOTAL"] = str(album.tracktotal)
        to_tag.save()

class TrackMetadata:
    def __init__(self):
        self.position = None
        self.title = None
        self.duration = None
        pass

    def get_duration_in_seconds(self):
        d = datetime.strptime(self.duration, "%M:%S")
        return d.minute*60 + d.second

class AlbumMetadata:
    def __init__(self):
        self.title = None
        self.genres = None
        self.artists = None
        self.year = None
        self.tracktotal = None

class DiscogsResource:
    def __init__(self, uri):
        self.resource_uri = uri

    @staticmethod
    def is_mine_resource(domain):
        return "api.discogs.com" == domain

    def process(self):
        from pycurl import Curl
        import json
        from io import BytesIO

        b = BytesIO()
        c = Curl()
        c.setopt(c.URL, self.resource_uri)
        c.setopt(c.USERAGENT, "FooBar/1.0")
        c.setopt(c.WRITEDATA, b)
        c.perform()

        response = json.loads(b.getvalue())

        album_meta = AlbumMetadata()
        # Album metadata
        album_meta.title = response["title"]
        album_meta.year = response["year"]
        album_meta.genres = response["genres"]

        artists = []
        for artist in response["artists"]:
            artists.append(artist["name"])

        album_meta.artists = ",".join(artists)
        album_meta.tracktotal = len(response["tracklist"])

        millis = []
        # Iterate over tracklist
        tracks_meta = []
        for track in response['tracklist']:
            meta = TrackMetadata()
            meta.duration = track["duration"]
            meta.position = track["position"]
            meta.title = track["title"]

            tracks_meta.append(meta)

        return (album_meta, tracks_meta)

    pass

from argparse import ArgumentParser
from urlparse import urlparse
import os
import taglib

parser = ArgumentParser()
parser.add_argument("directory_file", help="Directory where the album's files are, or single audio file", type=str)
parser.add_argument("-r", "--resource", help="Resource URI", type=str, required=True)
parser.add_argument("--rename", help="Rename the files too", type=str)

args = parser.parse_args()

uri = args.resource
directory_file = args.directory_file
domain = '{uri.netloc}'.format(uri=urlparse(uri))

# Find an handler for the resource passed by command line.
resource_handlers = [DiscogsResource]  # List all classes for resources management
try:
    handler = next(h(uri) for h in resource_handlers if h.is_mine_resource(domain))
except StopIteration:
    print("Cannot process resource %s", uri)
    exit(-1)

extensions = [".mp3"]  # List all compatible files

if os.path.isfile(directory_file):
    files = [directory_file]
elif os.path.isdir(directory_file):
    files = [os.path.join(directory_file, f) for f in os.listdir(directory_file)]
else:
    print("No such file or directory, %s", directory_file)
    exit(-1)

tagged_file = [taglib.File(filename) for filename in files]

album, tracks = handler.process()

add_album_metadata(album, tagged_file)

def filter_filename(filename):
    # Filtering out names
    separator = ['-', '_']

    filename = filename.replace("-", " ")
    filename = filename.replace("_", " ")
    return filename

def levenshtein(s1, s2):
    if len(s1) < len(s2):
        return levenshtein(s2, s1)

    # len(s1) >= len(s2)
    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1 # j+1 instead of j since previous_row and current_row are one character longer
            deletions = current_row[j] + 1       # than s2
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]

from difflib import get_close_matches
def get_match_rank(track, tagged_file):
    """

    :param track:
    :param files:
    :type track: TrackMetadata
    :return:
    """
    filenames = [filter_filename(os.path.splitext(os.path.basename(filename.path))[0]) for filename in tagged_file]

    rank1 = [0]*len(tagged_file)
    # Alphabetically closest
    lowest = 100000
    index = -1
    values = [0]*len(tagged_file)
    for filename in filenames:
        value = levenshtein(track.title, filename)
        values[filenames.index(filename)] = value
        if value < lowest:
            lowest = value
            index = filenames.index(filename)
    print index

    closest = get_close_matches(track.title, filenames)
    if index != -1:
        rank1[index] = 1

    rank2 = [0]*len(tagged_file)
    closest = min(tagged_file, key=lambda x: abs(track.get_duration_in_seconds() - x.length))
    rank2[tagged_file.index(closest)] = 1

    final_ranks = [0.5*rank1[i] + 0.5*rank2[i] for i in xrange(0, len(rank1))]
    return final_ranks

old_tagged = tagged_file[:]
successfully_tagged = []
while len(successfully_tagged) != len(tracks):
    for track in tracks:
        if track in successfully_tagged:
            continue

        rank = get_match_rank(track, tagged_file)
        print("Do you want to associate these metadata with the file: " + tagged_file[rank.index(max(rank))].path)
        print("\t Track number: " + track.position)
        print("\t Track title: " + track.title)
        print("\t Track duration: " + track.duration)
        confirm = raw_input("[Y/n]:")

        if confirm == "Y":
            add_track_metadata(tagged_file[rank.index(max(rank))], track)
            tagged_file.remove(tagged_file[rank.index(max(rank))])
            successfully_tagged.append(track)
tagged_file = old_tagged

if args.rename:
    for tagged in tagged_file:
        new_name = args.rename
        new_name = new_name.replace("%no", tagged.tags["TRACKNUMBER"])
        new_name = new_name.replace("%track", tagged.tags["TITLE"])
        directory = os.path.dirname(tagged.path)
        extension = os.path.splitext(tagged.path)[1]
        os.rename(tagged.path, directory + "/" + new_name + extension)
