# Music Monster

Music Monster is a Flask web app that turns a user's nine life-defining albums into a unique monster card.

## How it works

1. The user enters exactly nine album title and artist pairs.
2. A fixed Replicate text model starts a constrained, creative visual-profile analysis. The browser checks its status until it finishes, so a cold model start does not exceed the web request timeout.
3. The profile selects exactly five distinct recognised genre keys from `data/genre_weights.yaml` and supplies visual traits.
4. The existing scoring system selects a creature template and Replicate generates the card image.

The form can remember confirmed albums in that browser's `localStorage`, so later visits can reuse them without an external music account. The app does not receive or store this local list until the user chooses to analyse a nine-album selection. The text model never writes to `genre_weights.yaml`. Submitted title and artist text is used only for the analysis request. The app caches an anonymous analysis result for 30 minutes to avoid repeat processing and does not store submitted album names.

Render logs include two structured JSON events for debugging: `album_taste_analysis` (the derived genre and visual profile) and `image_generation_request` (the derived profile plus the final image prompt). They intentionally exclude submitted album titles and artist names.

## Setup

Install dependencies with `pip install -r requirements.txt`, then configure Redis and the following environment variables:

```text
REDIS_URL=redis://...
FLASK_SECRET_KEY=...
REPLICATE_API_TOKEN=...
REPLICATE_TEXT_MODEL=owner/model-name
REPLICATE_IMAGE_MODEL_VERSION=optional-pinned-version-id
```

Start the application with `gunicorn app:app`.

## Production requirements

Pin both Replicate models to reviewed versions before deployment. Confirm each model's commercial-use licence, output terms, and input-data handling terms. The text model must accept a `prompt` input and return text. The current text-model prompt is designed for `meta/meta-llama-3-70b` and treats user album metadata as untrusted data, while requiring JSON-only output and category names copied exactly from the YAML-backed allow-list.

## Licence

MIT
