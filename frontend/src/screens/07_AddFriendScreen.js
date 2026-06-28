import React, {useEffect, useRef, useState} from 'react';
import {
  View,
  Text,
  ScrollView,
  Image,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  PermissionsAndroid,
  ActivityIndicator,
} from 'react-native';
import {launchCamera, launchImageLibrary} from 'react-native-image-picker';
import AudioRecord from '../services/audioRecorder';
import {
  ScreenBg,
  TopBar,
  LightInput,
  DarkBtn,
  BackBtn,
  COLORS,
} from '../components/UI';
import {useAuth} from '../../App';
import {BASE_URL} from '../config';

const API_URL = BASE_URL;
const MIN_PHOTOS = 1;
const REQUIRED_VOICE_SAMPLES = 3;
const VOICE_SAMPLE_SECONDS = 5;

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

async function requestMicPermission() {
  if (Platform.OS !== 'android') return true;
  try {
    const granted = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
      {
        title: 'Microphone Permission',
        message: 'Alzemora needs microphone access to record voice samples.',
        buttonPositive: 'Allow',
        buttonNegative: 'Deny',
      },
    );
    return granted === PermissionsAndroid.RESULTS.GRANTED;
  } catch {
    return false;
  }
}

/* ─── Inline UploadBox ───────────────────────────────────── */
function UploadBox({photos, onPhotosChange}) {
  const openCamera = async () => {
    const allowed = await requestCameraPermission();
    if (!allowed) {
      Alert.alert('Permission Denied', 'Enable camera permission in phone Settings.');
      return;
    }
    launchCamera(
      {mediaType: 'photo', quality: 0.8, saveToPhotos: false, cameraType: 'back'},
      response => {
        if (response.didCancel) return;
        if (response.errorCode) {
          Alert.alert('Camera Error', response.errorMessage || 'Could not open camera.');
          return;
        }
        const uri = response.assets?.[0]?.uri;
        if (uri) onPhotosChange([uri]);
      },
    );
  };

  const openGallery = async () => {
    const allowed = await requestStoragePermission();
    if (!allowed) {
      Alert.alert('Permission Denied', 'Enable storage permission in phone Settings.');
      return;
    }
    launchImageLibrary(
      {
        mediaType: 'photo',
        quality: 0.8,
        selectionLimit: 1,
        includeBase64: false,
      },
      response => {
        if (response.didCancel) return;
        if (response.errorCode) {
          Alert.alert('Gallery Error', response.errorMessage || 'Could not open gallery.');
          return;
        }
        const uris = response.assets?.map(a => a.uri).filter(Boolean) ?? [];
        if (uris.length > 0) onPhotosChange([uris[0]]);
      },
    );
  };

  const handlePress = () => {
    Alert.alert('Add Photo', 'Choose a source', [
      {text: 'Camera', onPress: openCamera},
      {text: 'Photo Library', onPress: openGallery},
      {text: 'Cancel', style: 'cancel'},
    ]);
  };

  return (
    <View style={styles.uploadContainer}>
      {photos.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.thumbRow}>
            {photos.map((uri, i) => (
              <View key={i} style={styles.thumbWrapper}>
                <Image source={{uri}} style={styles.thumb} />
                <TouchableOpacity
                  style={styles.thumbRemove}
                  onPress={() => onPhotosChange(photos.filter((_, idx) => idx !== i))}>
                  <Text style={styles.thumbRemoveText}>X</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </ScrollView>
      )}

      {photos.length < MIN_PHOTOS && (
        <TouchableOpacity
          activeOpacity={0.75}
          style={styles.uploadBox}
          onPress={handlePress}>
          <Text style={styles.uploadPlus}>+</Text>
          <Text style={styles.uploadHint}>Tap to add photo</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

/* ─── Main Screen ────────────────────────────────────────── */
export default function AddFriendScreen({navigation}) {
  const {user} = useAuth();

  const [name, setName] = useState('');
  const [relationship, setRelationship] = useState('');
  const [photos, setPhotos] = useState([]);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [voiceSamples, setVoiceSamples] = useState([]);
  const [isRecording, setIsRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState('');

  const stopTimeoutRef = useRef(null);

  useEffect(() => {
    return () => {
      if (stopTimeoutRef.current) {
        clearTimeout(stopTimeoutRef.current);
      }
    };
  }, []);

  const isValid = name.trim().length > 0;

  const targetUserId =
    user?.role === 'Guardian' || user?.role === 'CareGiver'
      ? user?.patient_id
      : user?.user_id;

  const normalizeFileUri = filePath =>
    filePath?.startsWith('file://') ? filePath : `file://${filePath}`;

  const safeVoiceFolderName = input =>
    input
      .trim()
      .replace(/[<>:"/\\|?*]+/g, '_')
      .replace(/\s+/g, ' ');

  const stopVoiceRecording = async () => {
    const rawPath = await AudioRecord.stop();
    setIsRecording(false);
    if (stopTimeoutRef.current) {
      clearTimeout(stopTimeoutRef.current);
      stopTimeoutRef.current = null;
    }
    return rawPath;
  };

  const handleRecordSample = async () => {
    if (!voiceEnabled || isRecording) return;

    if (!name.trim()) {
      Alert.alert('Name Required', 'Enter friend name before recording voice samples.');
      return;
    }
    if (voiceSamples.length >= REQUIRED_VOICE_SAMPLES) {
      Alert.alert('Completed', 'You already recorded all 3 voice samples.');
      return;
    }

    const micAllowed = await requestMicPermission();
    if (!micAllowed) {
      Alert.alert('Permission Denied', 'Enable microphone permission in phone Settings.');
      return;
    }

    try {
      AudioRecord.init({
        sampleRate: 16000,
        channels: 1,
        bitsPerSample: 16,
        wavFile: `voice_sample_${voiceSamples.length + 1}.wav`,
      });

      AudioRecord.start();
      setIsRecording(true);

      stopTimeoutRef.current = setTimeout(async () => {
        try {
          const rawPath = await stopVoiceRecording();
          if (!rawPath) {
            Alert.alert('Recording Error', 'No audio file was captured. Please try again.');
            return;
          }

          const sampleNumber = voiceSamples.length + 1;
          setVoiceSamples(prev => [
            ...prev,
            {
              uri: normalizeFileUri(rawPath),
              name: `${safeVoiceFolderName(name)}_sample_${sampleNumber}.wav`,
            },
          ]);

          Alert.alert('Recorded', `Voice sample ${sampleNumber}/${REQUIRED_VOICE_SAMPLES} saved.`);
        } catch {
          setIsRecording(false);
          Alert.alert('Recording Error', 'Could not save voice sample. Please try again.');
        }
      }, VOICE_SAMPLE_SECONDS * 1000);
    } catch {
      setIsRecording(false);
      Alert.alert('Recording Error', 'Could not start microphone recording.');
    }
  };

  const handleResetVoiceSamples = () => {
    if (isRecording) {
      Alert.alert('Please Wait', 'Recording is in progress.');
      return;
    }
    setVoiceSamples([]);
  };

  const handleAdd = async () => {
    if (!name.trim()) {
      Alert.alert('Missing Info', 'Please enter the person\'s name.');
      return;
    }
    if (photos.length < MIN_PHOTOS) {
      Alert.alert('Photo Required', `Please add at least ${MIN_PHOTOS} photo.`);
      return;
    }
    if (voiceEnabled && voiceSamples.length < REQUIRED_VOICE_SAMPLES) {
      Alert.alert(
        'Voice Samples Required',
        `Please record ${REQUIRED_VOICE_SAMPLES} samples (${VOICE_SAMPLE_SECONDS} seconds each).`,
      );
      return;
    }
    if (!targetUserId) {
      Alert.alert('Error', 'Could not determine patient account. Please log in again.');
      return;
    }

    setLoading(true);

    try {
      const uri = photos[0];
      const filename = uri.split('/').pop() || 'photo.jpg';
      const ext = filename.split('.').pop()?.toLowerCase() || 'jpg';
      const mimeType = ext === 'png' ? 'image/png' : 'image/jpeg';

      setStatusText('Uploading photo...');

      const formData = new FormData();
      formData.append('user_id', targetUserId);
      formData.append('name', name.trim());
      formData.append('relation', relationship.trim() || '');
      formData.append('face_file', {
        uri,
        name: filename,
        type: mimeType,
      });

      if (voiceEnabled && voiceSamples.length === REQUIRED_VOICE_SAMPLES) {
        setStatusText('Uploading voice samples...');
        voiceSamples.forEach(sample => {
          formData.append('voice_files', {
            uri: sample.uri,
            name: sample.name,
            type: 'audio/wav',
          });
        });
      }

      const response = await fetch(`${API_URL}/register-person`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (data.error) {
        Alert.alert('Failed', data.error);
        setLoading(false);
        setStatusText('');
        return;
      }

      setStatusText('');
      Alert.alert(
        'Friend Added',
        `${name} has been registered as a friend for ${data.patient_name || 'the patient'}.`,
        [{text: 'OK', onPress: () => navigation.navigate('Dashboard')}],
      );
    } catch {
      Alert.alert(
        'Connection Error',
        'Could not reach the server. Make sure your backend is running and you are on the same Wi-Fi.',
      );
    } finally {
      setLoading(false);
      setStatusText('');
    }
  };

  return (
    <ScreenBg>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={StyleSheet.absoluteFill}>
        <TopBar navigation={navigation} />

        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}>
          <LightInput
            label="Name:"
            placeholder="Enter full name"
            value={name}
            onChangeText={setName}
          />

          <LightInput
            label="Relationship:"
            placeholder="e.g. Son, Daughter, Sibling..."
            value={relationship}
            onChangeText={setRelationship}
          />

          <View style={styles.sectionRow}>
            <Text style={styles.sectionTitle}>Insert image</Text>
            <Text style={styles.sectionHint}>
              {photos.length}/{MIN_PHOTOS} required {photos.length >= MIN_PHOTOS ? 'OK' : ''}
            </Text>
          </View>

          <UploadBox photos={photos} onPhotosChange={setPhotos} />

          {photos.length < MIN_PHOTOS && (
            <Text style={styles.photoHint}>{MIN_PHOTOS - photos.length} more photo required</Text>
          )}

          <View style={styles.voiceSection}>
            <View style={styles.voiceHeader}>
              <Text style={styles.sectionTitle}>Add voice (optional)</Text>
              <TouchableOpacity
                style={[styles.toggleBtn, voiceEnabled && styles.toggleBtnActive]}
                onPress={() => {
                  const enabled = !voiceEnabled;
                  setVoiceEnabled(enabled);
                  if (!enabled) {
                    setVoiceSamples([]);
                  }
                }}
                disabled={isRecording}
                activeOpacity={0.8}>
                <Text style={[styles.toggleBtnText, voiceEnabled && styles.toggleBtnTextActive]}>
                  {voiceEnabled ? 'Enabled' : 'Enable'}
                </Text>
              </TouchableOpacity>
            </View>

            {voiceEnabled && (
              <>
                <Text style={styles.voiceHint}>
                  Record 3 samples, each exactly 5 seconds. Files are uploaded as WAV.
                </Text>

                <Text style={styles.voiceProgress}>
                  {voiceSamples.length}/{REQUIRED_VOICE_SAMPLES} samples recorded
                </Text>

                <View style={styles.voiceActions}>
                  <TouchableOpacity
                    style={[styles.voiceBtn, isRecording && styles.voiceBtnDisabled]}
                    onPress={handleRecordSample}
                    disabled={isRecording || voiceSamples.length >= REQUIRED_VOICE_SAMPLES}
                    activeOpacity={0.8}>
                    <Text style={styles.voiceBtnText}>
                      {isRecording
                        ? `Recording... (${VOICE_SAMPLE_SECONDS}s)`
                        : voiceSamples.length >= REQUIRED_VOICE_SAMPLES
                          ? 'All samples recorded'
                          : `Record sample ${voiceSamples.length + 1}`}
                    </Text>
                  </TouchableOpacity>

                  <TouchableOpacity
                    style={styles.resetBtn}
                    onPress={handleResetVoiceSamples}
                    disabled={isRecording}
                    activeOpacity={0.8}>
                    <Text style={styles.resetBtnText}>Reset voice</Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </View>

          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={COLORS.white} />
              <Text style={styles.loadingText}>{statusText || 'Processing...'}</Text>
            </View>
          ) : (
            <DarkBtn title="Add Friend!" onPress={handleAdd} disabled={!isValid} style={styles.addBtn} />
          )}

          <BackBtn onPress={() => navigation.navigate('Dashboard')} />
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: 18,
    paddingTop: 10,
    paddingBottom: Platform.OS === 'ios' ? 50 : 30,
  },
  sectionRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 8,
    marginBottom: 10,
  },
  sectionTitle: {fontSize: 18, fontWeight: '500', color: COLORS.white},
  sectionHint: {fontSize: 12, fontWeight: '200', color: 'rgba(255,255,255,0.6)'},
  uploadContainer: {gap: 10, marginBottom: 8},
  thumbRow: {flexDirection: 'row', gap: 10, paddingBottom: 4},
  thumbWrapper: {position: 'relative'},
  thumb: {
    width: 80,
    height: 80,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: COLORS.teal,
  },
  thumbRemove: {
    position: 'absolute',
    top: -6,
    right: -6,
    backgroundColor: '#e74c3c',
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  thumbRemoveText: {color: '#fff', fontSize: 10, fontWeight: '700'},
  uploadBox: {
    backgroundColor: COLORS.inputLight,
    borderWidth: 1,
    borderColor: COLORS.inputBorder,
    borderRadius: 20,
    height: 120,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  uploadPlus: {fontSize: 36, color: '#bbb'},
  uploadHint: {fontSize: 13, fontWeight: '300', color: '#aaa'},
  photoHint: {
    fontSize: 12,
    fontWeight: '300',
    color: 'rgba(255,200,100,0.8)',
    marginBottom: 6,
    marginLeft: 4,
  },
  voiceSection: {
    marginTop: 14,
    marginBottom: 8,
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.18)',
    backgroundColor: 'rgba(255,255,255,0.06)',
    gap: 8,
  },
  voiceHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  toggleBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.14)',
  },
  toggleBtnActive: {
    backgroundColor: COLORS.teal,
  },
  toggleBtnText: {
    color: COLORS.white,
    fontSize: 12,
    fontWeight: '500',
  },
  toggleBtnTextActive: {
    color: COLORS.white,
  },
  voiceHint: {
    color: 'rgba(255,255,255,0.75)',
    fontSize: 12,
    fontWeight: '300',
    lineHeight: 18,
  },
  voiceProgress: {
    color: COLORS.white,
    fontSize: 13,
    fontWeight: '500',
  },
  voiceActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  voiceBtn: {
    flex: 1,
    backgroundColor: '#1f8f7a',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    alignItems: 'center',
  },
  voiceBtnDisabled: {
    opacity: 0.6,
  },
  voiceBtnText: {
    color: COLORS.white,
    fontSize: 12,
    fontWeight: '600',
  },
  resetBtn: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderRadius: 10,
    paddingVertical: 10,
    paddingHorizontal: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  resetBtnText: {
    color: COLORS.white,
    fontSize: 12,
    fontWeight: '500',
  },
  loadingContainer: {
    marginTop: 18,
    alignItems: 'center',
    gap: 10,
  },
  loadingText: {
    fontSize: 13,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.6)',
  },
  addBtn: {marginTop: 18, marginBottom: 4},
});
