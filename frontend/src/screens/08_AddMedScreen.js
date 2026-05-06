import React, {useEffect, useRef, useState} from 'react';
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  Alert,
  TouchableOpacity,
  Modal,
  ActivityIndicator,
} from 'react-native';
import {
  ScreenBg,
  TopBar,
  LightInput,
  DarkBtn,
  BackBtn,
  UploadBox,
  SectionTitle,
  COLORS,
} from '../components/UI';
import {useAuth} from '../../App';
import {addMedication, detectMedicationFromImage} from '../services/medicationService';

const DAY_OPTIONS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const HOUR_OPTIONS = Array.from({length: 12}, (_, i) => String(i + 1).padStart(2, '0'));
const MINUTE_OPTIONS = Array.from({length: 60}, (_, i) => String(i).padStart(2, '0'));
const PERIOD_OPTIONS = ['AM', 'PM'];

const SLOT_ITEM_HEIGHT = 38;
const SLOT_VISIBLE_ROWS = 5;
const SLOT_PICKER_HEIGHT = SLOT_ITEM_HEIGHT * SLOT_VISIBLE_ROWS;
const SLOT_CENTER_OFFSET = ((SLOT_VISIBLE_ROWS - 1) / 2) * SLOT_ITEM_HEIGHT;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

export default function AddMedScreen({navigation}) {
  const {user} = useAuth();
  
  // ADD tab state
  const [name,     setName]     = useState('');
  const [selDays,  setSelDays]  = useState(['Mon']);
  const [selHour,  setSelHour]  = useState('08');
  const [selMin,   setSelMin]   = useState('00');
  const [selPeriod, setSelPeriod] = useState('AM');
  const [photos, setPhotos] = useState([]);
  const [isSaving, setIsSaving] = useState(false);
  const [showDaysModal, setShowDaysModal] = useState(false);
  const [showTimeModal, setShowTimeModal] = useState(false);
  const [isDetecting, setIsDetecting] = useState(false);
  const [detectedName, setDetectedName] = useState(null);
  const [detectionConfidence, setDetectionConfidence] = useState(0);


  const [tempDays, setTempDays] = useState(selDays);
  const [tempDay, setTempDay] = useState(selDays[0] || 'Mon');
  const [tempHour, setTempHour] = useState(selHour);
  const [tempMin, setTempMin] = useState(selMin);
  const [tempPeriod, setTempPeriod] = useState(selPeriod);

  const dayScrollRef = useRef(null);
  const hourScrollRef = useRef(null);
  const minuteScrollRef = useRef(null);
  const periodScrollRef = useRef(null);

  const dayLabel = selDays.length ? selDays.join(', ') : 'Choose days';
  const selectedTimeLabel = `${selHour}:${selMin} ${selPeriod}`;
  const isHelper = user?.role === 'Guardian' || user?.role === 'CareGiver';
  const targetPatientId = isHelper ? user?.patient_id : user?.user_id;
  const targetPatientName = isHelper ? user?.patient_name : user?.full_name;

  const openDaysModal = () => {
    const initialDay = selDays[0] || 'Mon';
    setTempDays(selDays);
    setTempDay(initialDay);
    setShowDaysModal(true);
  };

  const toggleTempDay = day => {
    setTempDays(prev => {
      if (prev.includes(day)) {
        return prev.filter(d => d !== day);
      }
      return [...prev, day];
    });
  };

  const openTimeModal = () => {
    setTempHour(selHour);
    setTempMin(selMin);
    setTempPeriod(selPeriod);
    setShowTimeModal(true);
  };

  const scrollToOption = (scrollRef, options, value) => {
    const index = Math.max(options.indexOf(value), 0);
    scrollRef.current?.scrollTo({
      y: index * SLOT_ITEM_HEIGHT,
      animated: false,
    });
  };

  const getOptionFromOffset = (offsetY, options) => {
    const index = clamp(
      Math.round(offsetY / SLOT_ITEM_HEIGHT),
      0,
      options.length - 1,
    );
    return options[index];
  };

  useEffect(() => {
    if (!showDaysModal) {
      return;
    }

    requestAnimationFrame(() => {
      scrollToOption(dayScrollRef, DAY_OPTIONS, tempDay);
    });
  }, [showDaysModal, tempDay]);

  useEffect(() => {
    if (!showTimeModal) {
      return;
    }

    requestAnimationFrame(() => {
      scrollToOption(hourScrollRef, HOUR_OPTIONS, tempHour);
      scrollToOption(minuteScrollRef, MINUTE_OPTIONS, tempMin);
      scrollToOption(periodScrollRef, PERIOD_OPTIONS, tempPeriod);
    });
  }, [showTimeModal, tempHour, tempMin, tempPeriod]);

  // Detect medication from first photo when photos are selected
  const handlePhotosChange = async (newPhotos) => {
    setPhotos(newPhotos);
    setDetectedName(null);
    setDetectionConfidence(0);

    // If first photo is added, attempt detection
    if (newPhotos.length > 0 && !name.trim()) {
      setIsDetecting(true);
      try {
        const result = await detectMedicationFromImage(newPhotos[0]);
        if (result?.detected_name) {
          setDetectedName(result.detected_name);
          setDetectionConfidence(result.confidence || 0);
          // Auto-populate name if confidence is high
          if (result.confidence > 0.7) {
            setName(result.detected_name);
          }
        }
      } catch (error) {
        console.log('[DETECTION] Detection failed:', error?.message);
      } finally {
        setIsDetecting(false);
      }
    }
  };

  const handleAdd = async () => {
    if (!name.trim()) {
      Alert.alert('Missing Info', 'Please enter the medication name.');
      return;
    }
    if (!targetPatientId) {
      Alert.alert('Missing Patient', 'Select a patient before adding medication.');
      return;
    }
    if (!photos.length) {
      Alert.alert('Missing Photo', 'Please add at least one medication picture.');
      return;
    }
    if (!selDays.length) {
      Alert.alert('Missing Info', 'Please choose at least one day.');
      return;
    }

    setIsSaving(true);
    try {
      const payload = await addMedication({
        patientId: targetPatientId,
        name: name.trim(),
        description: `${name.trim()} scheduled for ${selDays.join(', ')} at ${selectedTimeLabel}`,
        schedule: {
          days: selDays,
          time: selectedTimeLabel,
          hour: selHour,
          minute: selMin,
          period: selPeriod,
        },
        imageUris: photos,
        actorUserId: user?.user_id || user?._id || null,
        actorRole: user?.role || null,
      });

      Alert.alert(
        'Medication Saved',
        `${payload?.medication?.name || name.trim()} was added for ${targetPatientName || 'the patient'} with ${photos.length} photo${photos.length > 1 ? 's' : ''}.`,
        [{text: 'OK', onPress: () => {
          // Reset form
          setName('');
          setSelDays(['Mon']);
          setSelHour('08');
          setSelMin('00');
          setSelPeriod('AM');
          setPhotos([]);
          navigation.navigate('Dashboard');
        }}],
      );
    } catch (error) {
      Alert.alert('Save Failed', error?.message || 'Could not save medication.');
    } finally {
      setIsSaving(false);
    }
  };

  

  return (
    <ScreenBg>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={StyleSheet.absoluteFill}>

        <TopBar navigation={navigation} />

        {/* Add Med header */}

        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}>

          {/* ===== ADD MEDICATION ===== */}
              <LightInput
                label="Name:"
                placeholder="Medication name"
                value={name}
                onChangeText={setName}
              />

              {/* Time picker */}
              <Text style={styles.timeLabel}>Schedule:</Text>
              <View style={styles.slotGroup}>
                <Text style={styles.slotHeader}>Days</Text>
                <TouchableOpacity
                  onPress={openDaysModal}
                  style={styles.slotClosedBtn}
                  activeOpacity={0.85}>
                  <Text style={styles.slotClosedText} numberOfLines={1}>
                    {dayLabel}
                  </Text>
                </TouchableOpacity>
              </View>

              <View style={styles.slotGroup}>
                <Text style={styles.slotHeader}>Time</Text>
                <TouchableOpacity
                  onPress={openTimeModal}
                  style={styles.slotClosedBtn}
                  activeOpacity={0.85}>
                  <Text style={styles.slotClosedText}>{selectedTimeLabel}</Text>
                </TouchableOpacity>
              </View>

              <Text style={styles.timeHint}>
                Tap time to open wheel slots for hour, minute, and AM/PM
              </Text>

              <SectionTitle>Insert images</SectionTitle>
              <UploadBox photos={photos} onPhotosChange={handlePhotosChange} maxPhotos={5} />

              {isDetecting && (
                <View style={styles.detectionStatus}>
                  <ActivityIndicator size="small" color="#F8A42D" />
                  <Text style={styles.detectionStatusText}>Detecting medication...</Text>
                </View>
              )}

              {detectedName && !isDetecting && (
                <View style={styles.detectionResult}>
                  <Text style={styles.detectionResultTitle}>✓ Detected</Text>
                  <Text style={styles.detectionResultName}>{detectedName}</Text>
                  <Text style={styles.detectionResultConfidence}>
                    Confidence: {(detectionConfidence * 100).toFixed(0)}%
                  </Text>
                  {detectionConfidence < 0.7 && (
                    <Text style={styles.detectionResultHint}>Please verify or edit above</Text>
                  )}
                </View>
              )}

              <DarkBtn
                title={isSaving ? 'Saving...' : 'Add Med!'}
                onPress={handleAdd}
                style={styles.addBtn}
                disabled={isSaving}
              />
          <BackBtn onPress={() => navigation.navigate('Dashboard')} />
        </ScrollView>
      </KeyboardAvoidingView>

      <Modal
        visible={showDaysModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowDaysModal(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <TouchableOpacity onPress={() => setShowDaysModal(false)}>
                <Text style={styles.modalAction}>Cancel</Text>
              </TouchableOpacity>
              <Text style={styles.modalTitle}>Select Days</Text>
              <TouchableOpacity
                onPress={() => {
                  setSelDays(tempDays);
                  setShowDaysModal(false);
                }}>
                <Text style={styles.modalAction}>Save</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.wheelsRow}>
              <View style={styles.wheelColFull}>
                <Text style={styles.wheelTitle}>Day Slot</Text>
                <View style={styles.wheelBox}>
                  <View style={styles.wheelHighlight} />
                  <ScrollView
                    ref={dayScrollRef}
                    showsVerticalScrollIndicator={false}
                    snapToInterval={SLOT_ITEM_HEIGHT}
                    decelerationRate="fast"
                    contentContainerStyle={styles.wheelContent}
                    onMomentumScrollEnd={event =>
                      setTempDay(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          DAY_OPTIONS,
                        ),
                      )
                    }
                    onScrollEndDrag={event =>
                      setTempDay(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          DAY_OPTIONS,
                        ),
                      )
                    }>
                    {DAY_OPTIONS.map(option => (
                      <View key={option} style={styles.wheelItem}>
                        <Text
                          style={[
                            styles.wheelItemText,
                            tempDay === option && styles.wheelItemTextSelected,
                          ]}>
                          {option}
                        </Text>
                      </View>
                    ))}
                  </ScrollView>
                </View>
              </View>
            </View>

            <View style={styles.daysActionsRow}>
              <TouchableOpacity
                style={styles.daysToggleBtn}
                onPress={() => toggleTempDay(tempDay)}
                activeOpacity={0.85}>
                <Text style={styles.daysToggleText}>
                  {tempDays.includes(tempDay) ? 'Remove Day' : 'Add Day'}
                </Text>
              </TouchableOpacity>
            </View>

            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.daysChipsRow}>
              {tempDays.length ? (
                tempDays.map(day => (
                  <View key={day} style={styles.dayChipSelected}>
                    <Text style={styles.dayChipText}>{day}</Text>
                  </View>
                ))
              ) : (
                <Text style={styles.noDaysText}>No days selected yet</Text>
              )}
            </ScrollView>
          </View>
        </View>
      </Modal>

      <Modal
        visible={showTimeModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowTimeModal(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <TouchableOpacity onPress={() => setShowTimeModal(false)}>
                <Text style={styles.modalAction}>Cancel</Text>
              </TouchableOpacity>
              <Text style={styles.modalTitle}>Edit Alarm</Text>
              <TouchableOpacity
                onPress={() => {
                  setSelHour(tempHour);
                  setSelMin(tempMin);
                  setSelPeriod(tempPeriod);
                  setShowTimeModal(false);
                }}>
                <Text style={styles.modalAction}>Save</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.wheelsRow}>
              <View style={styles.wheelCol}>
                <Text style={styles.wheelTitle}>Hour</Text>
                <View style={styles.wheelBox}>
                  <View style={styles.wheelHighlight} />
                  <ScrollView
                    ref={hourScrollRef}
                    showsVerticalScrollIndicator={false}
                    snapToInterval={SLOT_ITEM_HEIGHT}
                    decelerationRate="fast"
                    contentContainerStyle={styles.wheelContent}
                    onMomentumScrollEnd={event =>
                      setTempHour(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          HOUR_OPTIONS,
                        ),
                      )
                    }
                    onScrollEndDrag={event =>
                      setTempHour(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          HOUR_OPTIONS,
                        ),
                      )
                    }>
                    {HOUR_OPTIONS.map(option => (
                      <View key={option} style={styles.wheelItem}>
                        <Text
                          style={[
                            styles.wheelItemText,
                            tempHour === option && styles.wheelItemTextSelected,
                          ]}>
                          {option}
                        </Text>
                      </View>
                    ))}
                  </ScrollView>
                </View>
              </View>

              <View style={styles.wheelCol}>
                <Text style={styles.wheelTitle}>Min</Text>
                <View style={styles.wheelBox}>
                  <View style={styles.wheelHighlight} />
                  <ScrollView
                    ref={minuteScrollRef}
                    showsVerticalScrollIndicator={false}
                    snapToInterval={SLOT_ITEM_HEIGHT}
                    decelerationRate="fast"
                    contentContainerStyle={styles.wheelContent}
                    onMomentumScrollEnd={event =>
                      setTempMin(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          MINUTE_OPTIONS,
                        ),
                      )
                    }
                    onScrollEndDrag={event =>
                      setTempMin(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          MINUTE_OPTIONS,
                        ),
                      )
                    }>
                    {MINUTE_OPTIONS.map(option => (
                      <View key={option} style={styles.wheelItem}>
                        <Text
                          style={[
                            styles.wheelItemText,
                            tempMin === option && styles.wheelItemTextSelected,
                          ]}>
                          {option}
                        </Text>
                      </View>
                    ))}
                  </ScrollView>
                </View>
              </View>

              <View style={styles.wheelColPeriod}>
                <Text style={styles.wheelTitle}>AM/PM</Text>
                <View style={styles.wheelBox}>
                  <View style={styles.wheelHighlight} />
                  <ScrollView
                    ref={periodScrollRef}
                    showsVerticalScrollIndicator={false}
                    snapToInterval={SLOT_ITEM_HEIGHT}
                    decelerationRate="fast"
                    contentContainerStyle={styles.wheelContent}
                    onMomentumScrollEnd={event =>
                      setTempPeriod(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          PERIOD_OPTIONS,
                        ),
                      )
                    }
                    onScrollEndDrag={event =>
                      setTempPeriod(
                        getOptionFromOffset(
                          event.nativeEvent.contentOffset.y,
                          PERIOD_OPTIONS,
                        ),
                      )
                    }>
                    {PERIOD_OPTIONS.map(option => (
                      <View key={option} style={styles.wheelItem}>
                        <Text
                          style={[
                            styles.wheelItemText,
                            tempPeriod === option && styles.wheelItemTextSelected,
                          ]}>
                          {option}
                        </Text>
                      </View>
                    ))}
                  </ScrollView>
                </View>
              </View>
            </View>
          </View>
        </View>
      </Modal>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  tabContainer: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 8,
    gap: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.08)',
  },
  tabButton: {
    flex: 1,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
    backgroundColor: 'rgba(255,255,255,0.05)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
  },
  tabButtonActive: {
    backgroundColor: 'rgba(248,164,45,0.15)',
    borderColor: '#F8A42D',
  },
  tabButtonText: {
    color: 'rgba(255,255,255,0.5)',
    fontSize: 13,
    fontWeight: '600',
    textAlign: 'center',
  },
  tabButtonTextActive: {
    color: '#F8A42D',
  },
  detectionStatus: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(248,164,45,0.08)',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginTop: 10,
    gap: 8,
  },
  detectionStatusText: {
    color: '#F8A42D',
    fontSize: 12,
    fontWeight: '500',
  },
  detectionResult: {
    backgroundColor: 'rgba(100,200,100,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(100,200,100,0.3)',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginTop: 10,
  },
  detectionResultTitle: {
    color: '#64C864',
    fontSize: 11,
    fontWeight: '600',
    marginBottom: 4,
  },
  detectionResultName: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 4,
  },
  detectionResultConfidence: {
    color: 'rgba(255,255,255,0.6)',
    fontSize: 11,
    fontWeight: '400',
  },
  detectionResultHint: {
    color: '#FFB84D',
    fontSize: 10,
    fontWeight: '400',
    marginTop: 6,
    fontStyle: 'italic',
  },
  singlePhotoContainer: {
    marginBottom: 12,
  },
  photoPreview: {
    backgroundColor: 'rgba(248,164,45,0.1)',
    borderWidth: 1,
    borderColor: '#F8A42D',
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  photoLabel: {
    color: '#F8A42D',
    fontSize: 14,
    fontWeight: '600',
  },
  removePhotoBtn: {
    backgroundColor: 'rgba(255,100,100,0.2)',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  removePhotoBtnText: {
    color: '#FF6464',
    fontSize: 12,
    fontWeight: '600',
  },
  recordBtn: {
    marginTop: 12,
    marginBottom: 4,
  },
  scroll: {
    paddingHorizontal: 18,
    paddingTop: 10,
    paddingBottom: Platform.OS === 'ios' ? 50 : 30,
  },
  timeLabel: {
    fontSize: 18,
    fontWeight: '500',
    color: COLORS.white,
    marginBottom: 10,
  },
  slotGroup: {
    marginBottom: 10,
  },
  slotHeader: {
    color: COLORS.white,
    fontSize: 12,
    fontWeight: '500',
    marginBottom: 6,
    marginLeft: 2,
  },
  slotClosedBtn: {
    backgroundColor: COLORS.inputLight,
    borderWidth: 1,
    borderColor: COLORS.inputBorder,
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  slotClosedText: {
    color: COLORS.text,
    fontSize: 13,
    fontWeight: '500',
    textAlign: 'center',
  },
  slotOpenPanel: {
    marginTop: 6,
  },
  slotScroller: {
    maxHeight: 190,
    backgroundColor: COLORS.inputLight,
    borderWidth: 1,
    borderColor: COLORS.inputBorder,
    borderRadius: 14,
  },
  slotContent: {
    paddingVertical: 8,
  },
  slotItem: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    marginHorizontal: 8,
    marginVertical: 2,
    borderRadius: 10,
  },
  slotItemSelected: {
    backgroundColor: COLORS.dark,
  },
  slotItemText: {
    fontSize: 13,
    fontWeight: '400',
    color: COLORS.text,
    textAlign: 'center',
  },
  slotItemTextSelected: {
    color: COLORS.white,
    fontWeight: '600',
  },
  doneBtn: {
    alignSelf: 'flex-end',
    marginTop: 8,
    backgroundColor: COLORS.dark,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  doneBtnText: {
    color: COLORS.white,
    fontSize: 13,
    fontWeight: '600',
  },
  wheelColFull: {
    flex: 1,
  },
  daysActionsRow: {
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingBottom: 10,
  },
  daysToggleBtn: {
    backgroundColor: COLORS.dark,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  daysToggleText: {
    color: COLORS.white,
    fontSize: 13,
    fontWeight: '600',
  },
  daysChipsRow: {
    paddingHorizontal: 12,
    paddingBottom: 14,
    gap: 8,
  },
  dayChipSelected: {
    backgroundColor: 'rgba(248,164,45,0.18)',
    borderColor: '#F8A42D',
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  dayChipText: {
    color: '#F8A42D',
    fontSize: 12,
    fontWeight: '600',
  },
  noDaysText: {
    color: 'rgba(255,255,255,0.5)',
    fontSize: 12,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'center',
    paddingHorizontal: 12,
  },
  modalCard: {
    backgroundColor: '#17181E',
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  modalAction: {
    color: '#F8A42D',
    fontSize: 15,
    fontWeight: '600',
  },
  modalTitle: {
    color: COLORS.white,
    fontSize: 15,
    fontWeight: '600',
  },
  wheelsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
    paddingHorizontal: 12,
    paddingTop: 14,
    paddingBottom: 16,
  },
  wheelCol: {
    flex: 1,
  },
  wheelColPeriod: {
    width: 84,
  },
  wheelTitle: {
    color: 'rgba(255,255,255,0.72)',
    fontSize: 11,
    marginBottom: 6,
    textAlign: 'center',
  },
  wheelBox: {
    height: SLOT_PICKER_HEIGHT,
    borderRadius: 12,
    backgroundColor: '#20222A',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    overflow: 'hidden',
  },
  wheelHighlight: {
    position: 'absolute',
    left: 8,
    right: 8,
    top: SLOT_CENTER_OFFSET,
    height: SLOT_ITEM_HEIGHT,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 8,
    zIndex: 2,
  },
  wheelContent: {
    paddingVertical: SLOT_CENTER_OFFSET,
  },
  wheelItem: {
    height: SLOT_ITEM_HEIGHT,
    justifyContent: 'center',
    alignItems: 'center',
  },
  wheelItemText: {
    color: 'rgba(255,255,255,0.38)',
    fontSize: 21,
    fontWeight: '500',
  },
  wheelItemTextSelected: {
    color: COLORS.white,
    fontWeight: '700',
  },
  timeHint: {
    fontSize: 11,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.45)',
    marginBottom: 18,
    marginLeft: 4,
  },
  addBtn: {
    marginTop: 16,
    marginBottom: 4,
  },
});
