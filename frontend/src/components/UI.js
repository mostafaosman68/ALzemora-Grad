import React from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  Image,
  ScrollView,
  StyleSheet,
  Dimensions,
  Platform,
  Alert,
  PermissionsAndroid,
} from 'react-native';
import {launchCamera, launchImageLibrary} from 'react-native-image-picker';

const {width, height} = Dimensions.get('window');

/* ─── Design tokens ─────────────────────────────────────── */
export const COLORS = {
  bgDark:      '#11232e',
  bgMid:       '#2a4a5c',
  card:        '#d9d9d9',
  inputGray:   '#8f8e8e',
  inputLight:  '#f2f2f7',
  inputBorder: '#e5e5ea',
  dark:        '#1c2120',
  teal:        '#7ecfd4',
  white:       '#ffffff',
  text:        '#1c2120',
  subtext:     '#555555',
  placeholder: '#888888',
};

export const logo = require('../assets/brain_logo.png');

/* ─── Permission helpers ─────────────────────────────────── */
async function requestCameraPermission() {
  if (Platform.OS !== 'android') return true;
  try {
    const granted = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.CAMERA,
      {
        title: 'Camera Permission',
        message: 'Alzemora needs access to your camera to take photos.',
        buttonPositive: 'Allow',
        buttonNegative: 'Deny',
      },
    );
    return granted === PermissionsAndroid.RESULTS.GRANTED;
  } catch {
    return false;
  }
}

async function requestStoragePermission() {
  if (Platform.OS !== 'android') return true;
  try {
    // Android 13+ uses READ_MEDIA_IMAGES instead of READ_EXTERNAL_STORAGE
    const permission =
      parseInt(Platform.Version, 10) >= 33
        ? PermissionsAndroid.PERMISSIONS.READ_MEDIA_IMAGES
        : PermissionsAndroid.PERMISSIONS.READ_EXTERNAL_STORAGE;

    const granted = await PermissionsAndroid.request(permission, {
      title: 'Storage Permission',
      message: 'Alzemora needs access to your photos.',
      buttonPositive: 'Allow',
      buttonNegative: 'Deny',
    });
    return granted === PermissionsAndroid.RESULTS.GRANTED;
  } catch {
    return false;
  }
}

/* ─── Full-screen dark gradient background ──────────────── */
export function ScreenBg({children, style}) {
  return (
    <View style={[styles.screenBg, style]}>
      <View style={styles.bgLayer1} />
      <View style={styles.bgLayer2} />
      <View style={StyleSheet.absoluteFill}>{children}</View>
    </View>
  );
}

/* ─── Brand header with brain logo ─────────────────────── */
export function BrandHeader() {
  return (
    <View style={styles.brandHeader}>
      <Image source={logo} style={styles.brandLogo} resizeMode="contain" />
    </View>
  );
}

/* ─── White bottom card ─────────────────────────────────── */
export function Card({children, topRightRadius = 60, style}) {
  return (
    <View style={[styles.card, {borderTopRightRadius: topRightRadius}, style]}>
      {children}
    </View>
  );
}

/* ─── Top navigation bar ─────────────────────────────────── */
export function TopBar({navigation, title = 'welcome, User!', leftElement, rightElement}) {
  return (
    <View style={styles.topBar}>
      <Image
        source={logo}
        style={styles.topBarAvatar}
        resizeMode="contain"
      />
      {leftElement ? <View style={styles.topBarLeft}>{leftElement}</View> : null}
      <Text style={styles.topBarTitle}>{title}</Text>
      {rightElement && (
        <View style={styles.topBarRight}>
          {rightElement}
        </View>
      )}
    </View>
  );
}

/* ─── Gray pill input ───────────────────────────────────── */
export function GrayInput({
  label,
  placeholder,
  value,
  onChangeText,
  secureTextEntry = false,
  keyboardType = 'default',
}) {
  return (
    <View style={styles.inputWrapper}>
      {label ? <Text style={styles.grayLabel}>{label}</Text> : null}
      <TextInput
        style={styles.grayInput}
        placeholder={placeholder}
        placeholderTextColor={COLORS.placeholder}
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize="none"
        autoCorrect={false}
      />
    </View>
  );
}

/* ─── Light bordered input (dark screens) ──────────────── */
export function LightInput({
  label,
  placeholder,
  value,
  onChangeText,
  secureTextEntry = false,
  keyboardType = 'default',
}) {
  return (
    <View style={styles.inputWrapper}>
      {label ? <Text style={styles.lightLabel}>{label}</Text> : null}
      <TextInput
        style={styles.lightInput}
        placeholder={placeholder}
        placeholderTextColor="#aaa"
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize="none"
        autoCorrect={false}
      />
    </View>
  );
}

/* ─── Dark pill CTA button ──────────────────────────────── */
export function DarkBtn({title, onPress, style, disabled = false}) {
  return (
    <TouchableOpacity
      style={[styles.darkBtn, disabled && styles.darkBtnDisabled, style]}
      onPress={onPress}
      activeOpacity={disabled ? 1 : 0.82}
      disabled={disabled}>
      <Text style={[styles.darkBtnText, disabled && styles.darkBtnTextDisabled]}>
        {title}
      </Text>
    </TouchableOpacity>
  );
}

/* ─── Back ghost button ─────────────────────────────────── */
export function BackBtn({onPress, label = '← Back'}) {
  return (
    <TouchableOpacity onPress={onPress} style={styles.backBtn}>
      <Text style={styles.backBtnText}>{label}</Text>
    </TouchableOpacity>
  );
}

/* ─── Section title row ─────────────────────────────────── */
export function SectionTitle({children, hint}) {
  return (
    <View style={styles.sectionTitleRow}>
      <Text style={styles.sectionTitle}>{children}</Text>
      {hint ? <Text style={styles.sectionHint}>{hint}</Text> : null}
    </View>
  );
}

/* ─── Image upload box with camera/gallery ──────────────── */
export function UploadBox({photos = [], onPhotosChange, maxPhotos = 5}) {

  const openCamera = async () => {
    const allowed = await requestCameraPermission();
    if (!allowed) {
      Alert.alert('Permission Denied', 'Camera permission is required. Please enable it in your phone Settings.');
      return;
    }
    launchCamera(
      {
        mediaType: 'photo',
        quality: 0.8,
        saveToPhotos: false,
        includeBase64: false,
        cameraType: 'back',
      },
      response => {
        console.log('Camera response:', JSON.stringify(response));
        if (response.didCancel) return;
        if (response.errorCode) {
          Alert.alert('Camera Error', response.errorMessage || 'Could not open camera.');
          return;
        }
        const uri = response.assets?.[0]?.uri;
        if (uri) {
          onPhotosChange?.([...photos, uri].slice(0, maxPhotos));
        }
      },
    );
  };

  const openGallery = async () => {
    const allowed = await requestStoragePermission();
    if (!allowed) {
      Alert.alert('Permission Denied', 'Storage permission is required. Please enable it in your phone Settings.');
      return;
    }
    launchImageLibrary(
      {
        mediaType: 'photo',
        quality: 0.8,
        selectionLimit: maxPhotos - photos.length,
        includeBase64: false,
      },
      response => {
        if (response.didCancel) return;
        if (response.errorCode) {
          Alert.alert('Gallery Error', response.errorMessage || 'Could not open gallery.');
          return;
        }
        const uris = response.assets?.map(a => a.uri).filter(Boolean) ?? [];
        if (uris.length > 0) {
          onPhotosChange?.([...photos, ...uris].slice(0, maxPhotos));
        }
      },
    );
  };

  const handlePress = () => {
    Alert.alert('Add Photo', 'Choose a source', [
      {text: 'Camera',        onPress: openCamera},
      {text: 'Photo Library', onPress: openGallery},
      {text: 'Cancel',        style: 'cancel'},
    ]);
  };

  const removePhoto = index => {
    onPhotosChange?.(photos.filter((_, i) => i !== index));
  };

  return (
    <View style={styles.uploadContainer}>
      {/* Thumbnails */}
      {photos.length > 0 && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.thumbRow}>
          {photos.map((uri, i) => (
            <View key={i} style={styles.thumbWrapper}>
              <Image source={{uri}} style={styles.thumb} />
              <TouchableOpacity
                style={styles.thumbRemove}
                onPress={() => removePhoto(i)}>
                <Text style={styles.thumbRemoveText}>✕</Text>
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>
      )}

      {/* Add button — hidden when max reached */}
      {photos.length < maxPhotos && (
        <TouchableOpacity
          activeOpacity={0.75}
          style={styles.uploadBox}
          onPress={handlePress}>
          <Text style={styles.uploadPlus}>＋</Text>
          <Text style={styles.uploadHint}>
            Tap to add photo ({photos.length}/{maxPhotos})
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

/* ─── Subtitle with optional link text ─────────────────── */
export function Subtitle({text, linkText, onLinkPress}) {
  return (
    <Text style={styles.subtitle}>
      {text}{' '}
      {linkText ? (
        <Text style={styles.subtitleLink} onPress={onLinkPress}>
          {linkText}
        </Text>
      ) : null}
    </Text>
  );
}

/* ─── Card title ────────────────────────────────────────── */
export function CardTitle({children}) {
  return <Text style={styles.cardTitle}>{children}</Text>;
}



/* ─── Styles ─────────────────────────────────────────────── */
const styles = StyleSheet.create({
  /* Background */
  screenBg: {flex: 1, backgroundColor: COLORS.bgDark},
  bgLayer1: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: COLORS.bgDark,
  },
  bgLayer2: {
    position: 'absolute',
    bottom: 0, left: 0, right: 0,
    height: height * 0.55,
    backgroundColor: COLORS.bgDark,
    opacity: 0.5,
  },

  /* Brand header */
  brandHeader: {
    height: height * 0.41,
    alignItems: 'center',
    justifyContent: 'flex-end',
    paddingBottom: 10,
  },
  brandLogo: {width: width * 0.62, height: width * 0.62},

  /* Card */
  card: {
    position: 'absolute',
    bottom: 0, left: 0, right: 0,
    top: height * 0.38,
    backgroundColor: COLORS.card,
    borderTopRightRadius: 60,
    paddingHorizontal: 24,
    paddingTop: 28,
    paddingBottom: 30,
  },

  /* Top bar */
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingTop: Platform.OS === 'ios' ? 56 : 38,
    paddingBottom: 8,
    gap: 14,
  },
  topBarAvatar: {
    width: 52, height: 52,
    borderRadius: 26,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.3)',
    backgroundColor: 'rgba(42,74,92,0.5)',
    padding: 4,
  },
  topBarTitle: {fontSize: 20, color: COLORS.white, fontWeight: '300'},
  topBarLeft: {
    marginLeft: -4,
  },
  topBarRight: {
    position: 'absolute',
    right: 18,
    top: Platform.OS === 'ios' ? 56 : 38,
    paddingTop: 8,
  },

  /* Inputs */
  inputWrapper: {marginBottom: 2},
  grayLabel: {
    fontSize: 13, fontWeight: '200',
    color: COLORS.text, marginBottom: 5, marginLeft: 4,
  },
  grayInput: {
    backgroundColor: COLORS.inputGray,
    borderRadius: 78, height: 58,
    paddingHorizontal: 22, fontSize: 17,
    color: '#4d4c4c', marginBottom: 14,
  },
  lightLabel: {
    fontSize: 18, fontWeight: '500',
    color: COLORS.white, marginBottom: 8,
  },
  lightInput: {
    backgroundColor: COLORS.inputLight,
    borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: 27, height: 54,
    paddingHorizontal: 20, fontSize: 16,
    color: COLORS.text, marginBottom: 14,
  },

  /* Dark button */
  darkBtn: {
    backgroundColor: COLORS.dark,
    borderRadius: 27, height: 54,
    alignItems: 'center', justifyContent: 'center',
    marginTop: 6,
  },
  darkBtnDisabled: {
    backgroundColor: 'rgba(28,33,32,0.35)',
  },
  darkBtnText: {
    fontSize: 20, fontWeight: '800',
    color: COLORS.white, letterSpacing: 0.4,
  },
  darkBtnTextDisabled: {
    color: 'rgba(255,255,255,0.4)',
  },

  /* Back button */
  backBtn: {alignItems: 'center', paddingVertical: 12, marginTop: 2},
  backBtnText: {
    fontSize: 14, fontWeight: '300',
    color: 'rgba(255,255,255,0.55)',
  },

  /* Section title */
  sectionTitleRow: {
    flexDirection: 'row', alignItems: 'baseline',
    gap: 8, marginBottom: 10,
  },
  sectionTitle: {fontSize: 18, fontWeight: '500', color: COLORS.white},
  sectionHint: {
    fontSize: 12, fontWeight: '200',
    color: 'rgba(255,255,255,0.6)',
  },

  /* Upload */
  uploadContainer: {gap: 10, marginBottom: 8},
  thumbRow: {flexDirection: 'row'},
  thumbWrapper: {marginRight: 10, position: 'relative'},
  thumb: {
    width: 80, height: 80,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: COLORS.teal,
  },
  thumbRemove: {
    position: 'absolute', top: -6, right: -6,
    backgroundColor: '#e74c3c',
    width: 22, height: 22, borderRadius: 11,
    alignItems: 'center', justifyContent: 'center',
  },
  thumbRemoveText: {color: '#fff', fontSize: 10, fontWeight: '700'},
  uploadBox: {
    backgroundColor: COLORS.inputLight,
    borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: 20, height: 120,
    alignItems: 'center', justifyContent: 'center', gap: 8,
  },
  uploadPlus: {fontSize: 36, color: '#bbb'},
  uploadHint: {fontSize: 13, fontWeight: '300', color: '#aaa'},

  /* Subtitle */
  subtitle: {
    fontSize: 11, fontWeight: '200',
    color: COLORS.text, marginBottom: 20,
  },
  subtitleLink: {textDecorationLine: 'underline', fontWeight: '400'},

  /* Card title */
  cardTitle: {
    fontSize: 34, fontWeight: '800',
    color: COLORS.text, marginBottom: 6,
  },
});