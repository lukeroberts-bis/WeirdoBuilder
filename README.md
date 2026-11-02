# Weirdo Builder

A local, dependency-free web app for building Sword Weirdos warbands. Choose a
points limit, recruit a leader and troops, select classes, buy attributes and
weapons, and track the roster cost. The browser validates point and roster
rules locally; Python serves the app and its static rule data.

## Run

From the project root, run:

```powershell
python app.py
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser. Stop the
server with `Ctrl+C`. The Python server provides the static game rules; roster
editing and saved warbands run in the browser. Choose **Save warband** to store
a roster in that browser's local storage. Use **Saved warbands** to view, load,
update, or delete saved rosters. Saved rosters and their portraits are not sent
to the server, and are available only in the same browser on the same device.
Clearing browser site data removes them.

Use **Add photo** or **Change photo** on a fighter's roster card. JPEG, PNG,
and WebP files are resized in the browser and stored locally with a saved
warband. Photos count toward the browser's local-storage quota; if a save
exceeds available storage, the app reports the error and leaves existing saved
warbands intact. Characters without an uploaded photo use an original, locally
generated illustrated portrait based on their first selected class.

## Rulebook points and roster rules

The class, weapon, and attribute point options are transcribed from the Sword
Weirdos source material included with this project. The app adds class,
attribute, and weapon costs to calculate each model. The selected classes also
determine the permitted weapon groups and enforce per-warband class limits.

Each warband has one leader. Leaders may take up to two classes and one
optional leader trait. Troops take one class. The optional Powerful-model rule
allows one large model per warband, up to 30 points; it cannot be the leader
and may take two classes. Other models are limited to 25 points. Warband
budgets default to 100 and offer the rulebook's 75-, 100-, and 125-point games.
The Hero/Villain leader trait doubles that model's point cost.

The builder tracks roster costs, classes, weapon proficiencies, and the
Powerful-model limit. It does not simulate class abilities, weapon properties,
spells, or the Powerful model's in-game recovery rule. Class cards include
short rule summaries. To update the transcribed point data, edit
`CLASS_PROFILES`, `ATTRIBUTE_COSTS`, `WEAPONS`, or `LEADER_TRAITS` in
`class_profiles.py`.

## AI disclaimer

This app was entirely vibe coded using GitHub Copilot. It was built through
iterative AI-assisted development rather than a traditional hand-crafted
specification and implementation process.

## Tests

```powershell
python -m unittest -v
```
