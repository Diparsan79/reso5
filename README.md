# nepali letterboxd

a simple movie/series watchlist app. dump stuff you want to watch, mark it watched, rate it.
i wanted to make a frontend for my API that i made through the week 4 but i haven't been able to 

## features

- register for an api key (saved in local storage)
- add movies or series with genre
- view your full watchlist
- filter by type or watched status
- search by title
- mark as watched
- rate (1-5) + write a review (only after marking watched)
- delete with confirmation popup
- basic stats (total, watched, avg rating, top genre)

## running

```
fastapi dev src/resolution_week5_flameX/main.py
```

then open http://127.0.0.1:8000
