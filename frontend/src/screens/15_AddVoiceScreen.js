import React, {useEffect, useRef, useState, useCallback} from 'react';
import {
  View,
  Text,
  Image,
  ScrollView,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  PermissionsAndroid,
  ActivityIndicator,
  Modal,
  FlatList,
} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import AudioRecord from '../services/audioRecorder';
import {ScreenBg, TopBar, DarkBtn, BackBtn, COLORS} from '../components/UI';
import {useAuth} from '../../App';
import {BASE_URL} from '../config';

const REQUIRED_SAMPLES = 4;
const SAMPLE_SECONDS = 5;

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

const getImageUrl = photoPath => {
  if (!photoPath) return null;
  const idx = photoPath.indexOf('/data/');
  if (idx === -1) return null;
  return `${BASE_URL}${photoPath.substring(idx)}`;
};

/* ─── Person row inside the dropdown modal ─────────────────── */
function PersonOption({person, onSelect}) {
  const imageUrl = getImageUrl(person.photo_url);
  return (
    <TouchableOpacity style={styles.optionRow} onPress={() => onSelect(person)} activeOpacity={0.75}>
      {imageUrl ? (
        <Image source={{uri: imageUrl}} style={styles.optionAvatar} resizeMode="cover" />
      ) : (
        <View style={styles.optionAvatarPlaceholder}>
          <Text style={styles.optionAvatarInitial}>{(person.name || '?')[0].toUpperCase()}</Text>
        </View>
      )}
      <View style={styles.optionInfo}>
        <Text style={styles.optionName}>{person.name}</Text>
        {person.relation ? (
          <Text style={styles.optionRelation}>{person.relation}</Text>
        ) : null}
      </View>
      <Text style={styles.optionChevron}>›</Text>
    </TouchableOpacity>
  );
}

/* ─── Single sample row ────────────────────────────────────── */
function SampleRow({index, sample, isRecording, onRecord}) {
  const isDone = !!sample;
  return (
    <View style={styles.sampleRow}>
      <View style={[styles.sampleIndex, isDone && styles.sampleIndexDone]}>
        <Text style={styles.sampleIndexText}>{isDone ? '✓' : index}</Text>
      </View>
      <Text style={[styles.sampleLabel, isDone && styles.sampleLabelDone]}>
        {isDone ? `Sample ${index} recorded` : `Sample ${index} (${SAMPLE_SECONDS}s)`}
      </Text>
      {!isDone && (
        <TouchableOpacity
          style={[styles.recordBtn, isRecording && styles.recordBtnActive]}
          onPress={onRecord}
          disabled={isRecording}
          activeOpacity={0.8}>
          <Text style={styles.recordBtnIcon}>{isRecording ? '⏺' : '🎙'}</Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

/* ─── Main Screen ──────────────────────────────────────────── */
export default function AddVoiceScreen({navigation}) {
  const {user} = useAuth();

  const [people, setPeople] = useState([]);
  const [fetchingPeople, setFetchingPeople] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selectedPerson, setSelectedPerson] = useState(null);

  const [voiceSamples, setVoiceSamples] = useState([]);
  const [recordingIndex, setRecordingIndex] = useState(null);
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [countdown, setCountdown] = useState(null);

  const stopTimeoutRef = useRef(null);
  const countdownRef = useRef(null);

  const targetUserId =
    user?.role === 'Guardian' || user?.role === 'CareGiver'
      ? user?.patient_id
      : user?.user_id;

  const loadPeople = useCallback(async () => {
    if (!targetUserId) return;
    setFetchingPeople(true);
    try {
      const res = await fetch(
        `${BASE_URL}/people/${encodeURIComponent(targetUserId)}?include_embeddings=false`,
        {headers: {Accept: 'application/json'}},
      );
      const data = await res.json();
      const all = Array.isArray(data?.people) ? data.people : [];
      // Only show people who have face recognition but no voice yet
      setPeople(all.filter(p => !p.has_voice));
    } catch {
      Alert.alert('Error', 'Could not load contacts. Check your connection.');
    } finally {
      setFetchingPeople(false);
    }
  }, [targetUserId]);

  useFocusEffect(
    useCallback(() => {
      loadPeople();
      return () => {
        if (stopTimeoutRef.current) clearTimeout(stopTimeoutRef.current);
        if (countdownRef.current) clearInterval(countdownRef.current);
      };
    }, [loadPeople]),
  );

  const handleSelectPerson = person => {
    setSelectedPerson(person);
    setDropdownOpen(false);
    setVoiceSamples([]);
  };

  const normalizeFileUri = path =>
    path?.startsWith('file://') ? path : `file://${path}`;

  const safeFolder = input =>
    input.trim().replace(/[<>:"/\\|?*]+/g, '_').replace(/\s+/g, ' ');

  const handleRecord = async sampleNumber => {
    if (recordingIndex !== null) return;
    if (!selectedPerson) {
      Alert.alert('Select Person', 'Choose a person from the dropdown first.');
      return;
    }

    const micAllowed = await requestMicPermission();
    if (!micAllowed) {
      Alert.alert('Permission Denied', 'Enable microphone permission in phone Settings.');
      return;
    }

    try {
      await AudioRecord.init({
        sampleRate: 16000,
        channels: 1,
        bitsPerSample: 16,
        wavFile: `voice_sample_${sampleNumber}.wav`,
      });

      await AudioRecord.start();
      setRecordingIndex(sampleNumber);
      setCountdown(SAMPLE_SECONDS);

      countdownRef.current = setInterval(() => {
        setCountdown(prev => {
          if (prev <= 1) {
            clearInterval(countdownRef.current);
            return null;
          }
          return prev - 1;
        });
      }, 1000);

      stopTimeoutRef.current = setTimeout(async () => {
        try {
          const rawPath = await AudioRecord.stop();
          await new Promise(resolve => setTimeout(resolve, 600));

          setRecordingIndex(null);
          clearInterval(countdownRef.current);
          setCountdown(null);

          if (!rawPath) {
            Alert.alert('Recording Error', 'No audio captured. Please try again.');
            return;
          }

          setVoiceSamples(prev => [
            ...prev,
            {
              uri: normalizeFileUri(rawPath),
              name: `${safeFolder(selectedPerson.name)}_sample_${sampleNumber}.wav`,
            },
          ]);
        } catch {
          setRecordingIndex(null);
          clearInterval(countdownRef.current);
          setCountdown(null);
          Alert.alert('Recording Error', 'Could not save sample. Please try again.');
        }
      }, SAMPLE_SECONDS * 1000);
    } catch {
      setRecordingIndex(null);
      clearInterval(countdownRef.current);
      setCountdown(null);
      Alert.alert('Recording Error', 'Could not start microphone recording.');
    }
  };

  const handleReset = () => {
    if (recordingIndex !== null) {
      Alert.alert('Please Wait', 'Recording is in progress.');
      return;
    }
    setVoiceSamples([]);
  };

  const handleSubmit = async () => {
    if (!selectedPerson) {
      Alert.alert('No Person Selected', 'Please select a person from the dropdown.');
      return;
    }
    if (voiceSamples.length < REQUIRED_SAMPLES) {
      Alert.alert('Incomplete', `Please record all ${REQUIRED_SAMPLES} voice samples before submitting.`);
      return;
    }
    if (!targetUserId) {
      Alert.alert('Error', 'Could not determine patient account. Please log in again.');
      return;
    }

    setLoading(true);
    setStatusText('Uploading voice samples...');

    try {
      const formData = new FormData();
      formData.append('user_id', targetUserId);
      formData.append('name', selectedPerson.name);

      voiceSamples.forEach((sample, idx) => {
        formData.append(`voice_file_${idx + 1}`, {
          uri: sample.uri,
          name: sample.name,
          type: 'audio/wav',
        });
      });

      const response = await fetch(`${BASE_URL}/add-voice`, {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        Alert.alert('Failed', data.error || data.detail || 'Server error. Please try again.');
        return;
      }

      setStatusText('');
      Alert.alert(
        'Voice Added',
        `Voice samples for ${selectedPerson.name} have been saved successfully.`,
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

  const nextSample = voiceSamples.length + 1;
  const allDone = voiceSamples.length >= REQUIRED_SAMPLES;
  const selectedImageUrl = selectedPerson ? getImageUrl(selectedPerson.photo_url) : null;

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

          <Text style={styles.pageTitle}>Add Voice</Text>
          <Text style={styles.pageSubtitle}>
            Select a contact who has face recognition but no voice recorded yet.
          </Text>

          {/* ── Person dropdown ─────────────────────────── */}
          <Text style={styles.fieldLabel}>Person:</Text>

          {fetchingPeople ? (
            <View style={styles.dropdownBtn}>
              <ActivityIndicator size="small" color={COLORS.teal} />
              <Text style={styles.dropdownBtnText}>Loading contacts...</Text>
            </View>
          ) : people.length === 0 && !selectedPerson ? (
            <View style={[styles.dropdownBtn, styles.dropdownBtnEmpty]}>
              <Text style={styles.dropdownBtnEmptyText}>
                All contacts already have voice recorded
              </Text>
            </View>
          ) : (
            <TouchableOpacity
              style={styles.dropdownBtn}
              onPress={() => setDropdownOpen(true)}
              activeOpacity={0.8}>
              {selectedPerson ? (
                <View style={styles.dropdownSelected}>
                  {selectedImageUrl ? (
                    <Image source={{uri: selectedImageUrl}} style={styles.dropdownAvatar} />
                  ) : (
                    <View style={styles.dropdownAvatarPlaceholder}>
                      <Text style={styles.dropdownAvatarInitial}>
                        {selectedPerson.name[0].toUpperCase()}
                      </Text>
                    </View>
                  )}
                  <View style={styles.dropdownSelectedInfo}>
                    <Text style={styles.dropdownSelectedName}>{selectedPerson.name}</Text>
                    {selectedPerson.relation ? (
                      <Text style={styles.dropdownSelectedRelation}>{selectedPerson.relation}</Text>
                    ) : null}
                  </View>
                  <Text style={styles.dropdownChevron}>▾</Text>
                </View>
              ) : (
                <>
                  <Text style={styles.dropdownPlaceholder}>Select a person...</Text>
                  <Text style={styles.dropdownChevron}>▾</Text>
                </>
              )}
            </TouchableOpacity>
          )}

          {/* ── Recording section (only when person selected) ─ */}
          {selectedPerson && (
            <View style={styles.samplesSection}>
              <View style={styles.samplesSectionHeader}>
                <Text style={styles.sectionTitle}>Voice Samples</Text>
                <Text style={styles.samplesProgress}>
                  {voiceSamples.length}/{REQUIRED_SAMPLES}
                </Text>
              </View>

              <Text style={styles.samplesHint}>
                Tap 🎙 to record each 5-second sample. They must be recorded in order.
              </Text>

              {recordingIndex !== null && countdown !== null && (
                <View style={styles.countdownBanner}>
                  <Text style={styles.countdownText}>
                    Recording sample {recordingIndex}... {countdown}s remaining
                  </Text>
                </View>
              )}

              {Array.from({length: REQUIRED_SAMPLES}, (_, i) => i + 1).map(i => (
                <SampleRow
                  key={i}
                  index={i}
                  sample={voiceSamples[i - 1]}
                  isRecording={recordingIndex === i}
                  onRecord={() => {
                    if (i !== nextSample) {
                      Alert.alert('In Order', `Please record sample ${nextSample} first.`);
                      return;
                    }
                    handleRecord(i);
                  }}
                />
              ))}

              {voiceSamples.length > 0 && !allDone && (
                <TouchableOpacity
                  style={styles.resetBtn}
                  onPress={handleReset}
                  disabled={recordingIndex !== null}
                  activeOpacity={0.8}>
                  <Text style={styles.resetBtnText}>Reset all samples</Text>
                </TouchableOpacity>
              )}
            </View>
          )}

          {selectedPerson && (
            loading ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={COLORS.white} />
                <Text style={styles.loadingText}>{statusText || 'Processing...'}</Text>
              </View>
            ) : (
              <DarkBtn
                title={allDone ? 'Save Voice' : `Record sample ${Math.min(nextSample, REQUIRED_SAMPLES)} of ${REQUIRED_SAMPLES}`}
                onPress={handleSubmit}
                disabled={!allDone}
                style={styles.submitBtn}
              />
            )
          )}

          <BackBtn onPress={() => navigation.navigate('Dashboard')} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* ── Dropdown modal ─────────────────────────────── */}
      <Modal
        visible={dropdownOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setDropdownOpen(false)}>
        <TouchableOpacity
          style={styles.modalBackdrop}
          activeOpacity={1}
          onPress={() => setDropdownOpen(false)}>
          <View style={styles.modalSheet} onStartShouldSetResponder={() => true}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Select Person</Text>
              <TouchableOpacity onPress={() => setDropdownOpen(false)} style={styles.modalClose}>
                <Text style={styles.modalCloseText}>✕</Text>
              </TouchableOpacity>
            </View>
            <Text style={styles.modalSubtitle}>
              Showing contacts with face recognition but no voice yet
            </Text>
            <FlatList
              data={people}
              keyExtractor={item => item._id}
              renderItem={({item}) => (
                <PersonOption person={item} onSelect={handleSelectPerson} />
              )}
              ItemSeparatorComponent={() => <View style={styles.optionSeparator} />}
              showsVerticalScrollIndicator={false}
              style={styles.optionList}
            />
          </View>
        </TouchableOpacity>
      </Modal>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  scroll: {
    paddingHorizontal: 18,
    paddingTop: 10,
    paddingBottom: Platform.OS === 'ios' ? 50 : 30,
  },
  pageTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: COLORS.white,
    marginBottom: 4,
  },
  pageSubtitle: {
    fontSize: 13,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.55)',
    marginBottom: 18,
    lineHeight: 19,
  },
  fieldLabel: {
    fontSize: 14,
    fontWeight: '500',
    color: COLORS.white,
    marginBottom: 6,
  },
  dropdownBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.1)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.2)',
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 18,
    gap: 10,
  },
  dropdownBtnEmpty: {
    justifyContent: 'center',
    borderStyle: 'dashed',
  },
  dropdownBtnEmptyText: {
    fontSize: 13,
    color: 'rgba(255,255,255,0.4)',
    fontStyle: 'italic',
    textAlign: 'center',
    flex: 1,
  },
  dropdownPlaceholder: {
    flex: 1,
    fontSize: 14,
    color: 'rgba(255,255,255,0.4)',
  },
  dropdownChevron: {
    fontSize: 16,
    color: 'rgba(255,255,255,0.5)',
  },
  dropdownSelected: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  dropdownAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.2)',
  },
  dropdownAvatarPlaceholder: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dropdownAvatarInitial: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.white,
  },
  dropdownSelectedInfo: {
    flex: 1,
  },
  dropdownSelectedName: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.white,
  },
  dropdownSelectedRelation: {
    fontSize: 12,
    color: COLORS.teal,
    marginTop: 1,
    textTransform: 'capitalize',
  },
  samplesSection: {
    marginTop: 4,
    padding: 14,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.15)',
    backgroundColor: 'rgba(255,255,255,0.05)',
    gap: 10,
  },
  samplesSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: '600',
    color: COLORS.white,
  },
  samplesProgress: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.teal,
    backgroundColor: 'rgba(126,207,212,0.15)',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 10,
  },
  samplesHint: {
    fontSize: 12,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.6)',
    lineHeight: 18,
  },
  countdownBanner: {
    backgroundColor: 'rgba(255,100,100,0.18)',
    borderRadius: 10,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderWidth: 1,
    borderColor: 'rgba(255,100,100,0.35)',
  },
  countdownText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#ff8080',
    textAlign: 'center',
  },
  sampleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.08)',
  },
  sampleIndex: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  sampleIndexDone: {backgroundColor: COLORS.teal},
  sampleIndexText: {color: COLORS.white, fontSize: 12, fontWeight: '700'},
  sampleLabel: {
    flex: 1,
    fontSize: 13,
    fontWeight: '400',
    color: 'rgba(255,255,255,0.65)',
  },
  sampleLabelDone: {color: COLORS.teal, fontWeight: '600'},
  recordBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: '#1f8f7a',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  recordBtnActive: {backgroundColor: '#c0392b'},
  recordBtnIcon: {fontSize: 18},
  resetBtn: {
    alignSelf: 'flex-start',
    paddingVertical: 6,
    paddingHorizontal: 14,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.12)',
    marginTop: 4,
  },
  resetBtnText: {color: 'rgba(255,255,255,0.7)', fontSize: 12, fontWeight: '500'},
  loadingContainer: {marginTop: 20, alignItems: 'center', gap: 10},
  loadingText: {fontSize: 13, fontWeight: '300', color: 'rgba(255,255,255,0.6)'},
  submitBtn: {marginTop: 20, marginBottom: 4},
  /* ── Modal ── */
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: '#14303d',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    paddingTop: 16,
    paddingHorizontal: 18,
    paddingBottom: Platform.OS === 'ios' ? 40 : 24,
    maxHeight: '75%',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  modalTitle: {fontSize: 18, fontWeight: '700', color: COLORS.white},
  modalClose: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: 'rgba(255,255,255,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalCloseText: {color: COLORS.white, fontSize: 13, fontWeight: '700'},
  modalSubtitle: {
    fontSize: 12,
    color: 'rgba(255,255,255,0.45)',
    marginBottom: 14,
  },
  optionList: {flexGrow: 0},
  optionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    gap: 12,
  },
  optionAvatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  optionAvatarPlaceholder: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionAvatarInitial: {fontSize: 20, fontWeight: '700', color: COLORS.white},
  optionInfo: {flex: 1},
  optionName: {fontSize: 15, fontWeight: '700', color: COLORS.white},
  optionRelation: {
    fontSize: 12,
    color: COLORS.teal,
    marginTop: 2,
    textTransform: 'capitalize',
  },
  optionChevron: {fontSize: 20, color: 'rgba(255,255,255,0.3)', fontWeight: '700'},
  optionSeparator: {height: 1, backgroundColor: 'rgba(255,255,255,0.07)'},
});
