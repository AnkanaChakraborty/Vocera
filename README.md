# Vocera

VOCERA is an AI-powered accessibility solution that converts live speech into near real-time sign language. Using Azure AI Speech, NLP, OpenAI embeddings, Azure AI Search, and Redis Cache, it maps spoken content to human-recorded sign gestures, enabling seamless, low-latency communication for deaf and hard-of-hearing users. 

# Vocera - Teams Meeting Side Panel

A private, per-person side panel inside a Teams meeting. You click
**Start** inside the panel, speak, and matching sign-language clips
play in that panel — visible only to you, the person who added it.
No one else in the meeting sees it or is affected by it.

## How the pieces fit together

- **`bridge_server.py`** runs on your machine. It does the actual work:
  listens to your mic via Azure Speech, maps recognized words to sign
  clips (same NLP logic as before), and serves both the video files
  and the panel's web page.
- **`web/tab.html`** is the panel itself — the Start/Stop button and
  the video player Teams renders inside the meeting.
- **`web/config.html`** is a one-time "Save" screen Teams shows the
  first time you add the app.
- **`manifest/`** is the Teams app package that tells Teams where to
  find all of the above.

Because Teams only loads tab content over HTTPS, you'll expose your
local server through a dev tunnel — your laptop is still doing all
the work, the tunnel just gives Teams an HTTPS door to knock on.

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```
Also make sure your usual NLTK data (`punkt`, `averaged_perceptron_tagger`,
`wordnet`, `stopwords`) is downloaded, same as before.

### 2. Add your Azure credentials
`Azure_keys.env`:
```
AZURE_SPEECH_KEY=your_key_here
AZURE_SPEECH_REGION=your_region_here
```

### 3. Run the bridge server
```bash
python bridge_server.py
```
It starts on `http://localhost:5000`.

### 4. Expose it over HTTPS with a dev tunnel
Using Microsoft's `devtunnel` CLI (or `ngrok http 5000` as an alternative):
```bash
devtunnel host -p 5000 --allow-anonymous
```
This prints a public HTTPS URL, e.g. `https://abcd1234.devtunnels.ms`.
Keep this terminal running — closing it takes your panel offline.

### 5. Point the manifest at your tunnel
Open `manifest/manifest.json` and replace every
`REPLACE_WITH_YOUR_TUNNEL_DOMAIN` with your tunnel's host (no `https://`
prefix in `validDomains`, but keep it in the URLs), e.g.:
```json
"validDomains": ["abcd1234.devtunnels.ms"]
```

### 6. Package and sideload the app
```bash
cd manifest
zip -r ../vocera-app.zip manifest.json color.png outline.png
```
In Teams: **Apps > Manage your apps > Upload an app > Upload a custom app**,
and select `vocera-app.zip`.
> This requires custom-app upload to be enabled on your tenant. On a
> work account, check with your Teams admin if you don't see this
> option — it's off by default on many managed tenants.

### 7. Add it to a meeting
During a live (or scheduled) meeting: click **Apps** in the meeting
toolbar, find **Vocera**, and add it. Click **Save** on the one-time
setup screen. It opens in your side panel.

## Using it

- Click **Start** in the panel — this calls your local bridge server
  and turns your microphone on.
- Speak normally. Recognized speech is mapped to sign-language clips,
  which play one after another in the panel.
- Click **Stop** to turn it off.
- Only you see this panel. Other participants see nothing added or
  changed on their side.

## Notes / limitations

- Every time you restart your dev tunnel without a reserved domain,
  you get a new URL, and you'll need to update `validDomains` and
  re-upload the app package. `devtunnel` and ngrok both support
  reserving a persistent subdomain if you want to avoid this.
- Because your mic, Azure key, and video clips all live on your own
  machine, this only works while your machine and tunnel are running
  — it won't work for anyone else, and it stops if your laptop sleeps.
- The panel is docked to the side, not floating over the video — that's
  the tradeoff for this being genuinely triggered from inside Teams.


Author and Owner - Ankana Chakraborty (ankanac@microsoft.com)
#
