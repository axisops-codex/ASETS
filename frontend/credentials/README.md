# Signing credentials — nothing in here is committed

- `play-service-account.json` — Google Play service-account key used by
  `eas submit -p android`. Create it in Google Cloud Console → the Play Console
  service account with *Release manager* access, then drop the JSON here.
- iOS credentials are managed by EAS (`eas credentials`) and stored on Expo's
  servers; nothing needs to live in this folder.

See `../../LAUNCH.md` §3 and §4.
