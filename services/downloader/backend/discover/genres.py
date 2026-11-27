GENRES = {
    "action": ("Action & Adventure", [28, 12], [10759]),
    "animation": ("Animation", [16], [16]),
    "comedy": ("Comedy", [35], [35]),
    "crime": ("Crime", [80], [80]),
    "documentary": ("Documentary", [99], [99]),
    "drama": ("Drama", [18], [18]),
    "family": ("Family", [10751], [10751]),
    "history": ("History", [36], []),
    "horror": ("Horror", [27], []),
    "kids": ("Kids", [], [10762]),
    "music": ("Music", [10402], []),
    "mystery": ("Mystery", [9648], [9648]),
    "reality": ("Reality", [], [10764]),
    "romance": ("Romance", [10749], []),
    "scifi": ("Sci-Fi & Fantasy", [878, 14], [10765]),
    "thriller": ("Thriller", [53], []),
    "war": ("War & Politics", [10752], [10768]),
    "western": ("Western", [37], [37]),
}


def genre_options():
    return [
        {
            "id": key,
            "label": label,
            "movie": movie,
            "tv": tv,
        }
        for key, (label, movie, tv) in GENRES.items()
    ]


def genre_ids_for(media_type, selected):
    index = 1 if media_type == "movie" else 2

    return sorted({
        genre_id
        for key in selected
        for genre_id in GENRES[key][index]
    })
