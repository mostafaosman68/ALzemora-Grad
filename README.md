# Alzemora Grad

## Run The Android App

These steps run the React Native app from `frontend` on an Android emulator.

### 1. Start an emulator

From the repo root:

```powershell
& "$env:ANDROID_HOME\emulator\emulator.exe" -list-avds
& "$env:ANDROID_HOME\emulator\emulator.exe" -avd Pixel_7
```

Wait until the emulator is attached:

```powershell
adb devices
adb shell getprop sys.boot_completed
```

`sys.boot_completed` should print `1`.

### 2. Install dependencies

```powershell
cd frontend
npm install
```

If Metro or Android complains about missing files inside `node_modules`, reinstall the broken package. These two were previously corrupted locally:

```powershell
Remove-Item -LiteralPath node_modules\react-native-screens -Recurse -Force
Remove-Item -LiteralPath node_modules\@react-navigation\core -Recurse -Force
npm install
```

### 3. Start Metro

```powershell
cd frontend
npm start -- --reset-cache
```

Metro should be available on port `8081`.

If port `8081` is already in use:

```powershell
netstat -ano | Select-String ':8081'
Stop-Process -Id <PID> -Force
npm start -- --reset-cache
```

### 4. Build, install, and launch Android

In another PowerShell window:

```powershell
cd frontend
npx react-native run-android --deviceId emulator-5554
```

If the app is already installed and Metro is running, you can relaunch it directly:

```powershell
adb shell am force-stop com.alzemora
adb shell monkey -p com.alzemora -c android.intent.category.LAUNCHER 1
```

### 5. Optional permissions for emulator testing

```powershell
adb shell pm grant com.alzemora android.permission.CAMERA
adb shell pm grant com.alzemora android.permission.RECORD_AUDIO
adb shell pm grant com.alzemora android.permission.POST_NOTIFICATIONS
```

## Android SDK Notes

This project currently needs Android SDK Build-Tools `34.0.0`.

Check it exists:

```powershell
Get-Content "$env:ANDROID_HOME\build-tools\34.0.0\source.properties"
```

If missing, install it with sdkmanager:

```powershell
& "$env:ANDROID_HOME\cmdline-tools\latest\bin\sdkmanager.bat" --sdk_root=$env:ANDROID_HOME "build-tools;34.0.0"
```

If `sdkmanager.bat` is missing, install Android command-line tools in Android Studio or download them from Google and place them under:

```text
%ANDROID_HOME%\cmdline-tools\latest
```

## Useful Checks

Foreground app:

```powershell
adb shell dumpsys window | Select-String -Pattern 'mCurrentFocus|mFocusedApp'
```

Metro logs:

```powershell
Get-Content frontend\metro_run.log -Tail 80
Get-Content frontend\metro_run.err.log -Tail 80
```

Recent app errors:

```powershell
adb logcat -d -t 250 | Select-String -Pattern 'FATAL EXCEPTION|ReactNativeJS|Unable to resolve|AndroidRuntime'
```
