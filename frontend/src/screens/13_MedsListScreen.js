import React, {useState, useCallback, useRef, useEffect} from 'react';
import {
  View,
  Text,
  ScrollView,
  Image,
  TouchableOpacity,
  StyleSheet,
  Alert,
  ActivityIndicator,
  Platform,
  Modal,
} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {ScreenBg, TopBar, COLORS} from '../components/UI';
import {useAuth} from '../../App';
import {BASE_URL} from '../config';
import {
  fetchPatientMedications,
  deleteMedication,
  updateMedicationSchedule,
} from '../services/medicationService';

// ─── Schedule picker constants (mirrors AddMedScreen) ────────────────────────
const DAY_OPTIONS    = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const HOUR_OPTIONS   = Array.from({length: 12}, (_, i) => String(i + 1).padStart(2, '0'));
const MINUTE_OPTIONS = Array.from({length: 60}, (_, i) => String(i).padStart(2, '0'));
const PERIOD_OPTIONS = ['AM', 'PM'];

const SLOT_ITEM_HEIGHT  = 38;
const SLOT_VISIBLE_ROWS = 5;
const SLOT_PICKER_HEIGHT = SLOT_ITEM_HEIGHT * SLOT_VISIBLE_ROWS;
const SLOT_CENTER_OFFSET = ((SLOT_VISIBLE_ROWS - 1) / 2) * SLOT_ITEM_HEIGHT;

const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

const getOptionFromOffset = (offsetY, options) =>
  options[clamp(Math.round(offsetY / SLOT_ITEM_HEIGHT), 0, options.length - 1)];

// ─── Helpers ──────────────────────────────────────────────────────────────────
const formatSchedule = (med) => {
  // Prefer explicit top-level date/time fields
  const days = Array.isArray(med?.date)
    ? med.date.join(', ')
    : typeof med?.date === 'string' ? med.date : null;
  const time = med?.time || null;
  if (days || time) {
    return [days, time].filter(Boolean).join(' • ');
  }
  // Fall back to nested schedule object
  const schedule = med?.schedule;
  if (!schedule) return 'No schedule set';
  if (typeof schedule === 'string') return schedule;
  const parts = [];
  if (Array.isArray(schedule.days) && schedule.days.length > 0) parts.push(schedule.days.join(', '));
  if (schedule.time) parts.push(schedule.time);
  else if (schedule.hour && schedule.minute && schedule.period) parts.push(`${schedule.hour}:${schedule.minute} ${schedule.period}`);
  return parts.length > 0 ? parts.join(' • ') : 'No schedule set';
};

const parseSchedule = (med) => {
  let days   = ['Mon'];
  let hour   = '08';
  let minute = '00';
  let period = 'AM';

  // Prefer top-level date/time fields
  if (med?.date) {
    days = Array.isArray(med.date) ? med.date : [med.date];
  }
  if (med?.time) {
    const m = med.time.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
    if (m) {
      hour   = m[1].padStart(2, '0');
      minute = m[2];
      period = m[3].toUpperCase();
    }
  }

  // Fall back to nested schedule object if top-level fields are absent
  if (!med?.date && !med?.time) {
    const schedule = med?.schedule;
    if (schedule && typeof schedule === 'object') {
      if (Array.isArray(schedule.days) && schedule.days.length > 0) days = schedule.days;
      if (schedule.hour)   hour   = schedule.hour;
      if (schedule.minute) minute = schedule.minute;
      if (schedule.period) period = schedule.period;
      else if (schedule.time) {
        const m = schedule.time.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
        if (m) { hour = m[1].padStart(2, '0'); minute = m[2]; period = m[3].toUpperCase(); }
      }
    }
  }
  return {days, hour, minute, period};
};

const getImageUrl = (photoPath) => {
  if (!photoPath) return null;
  const idx = photoPath.indexOf('/data/');
  if (idx === -1) return null;
  return `${BASE_URL}${photoPath.substring(idx)}`;
};

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function MedsListScreen({navigation}) {
  const {user} = useAuth();
  const [medications, setMedications] = useState([]);
  const [loading, setLoading]         = useState(false);
  const [deletingId, setDeletingId]   = useState(null);

  // Edit state
  const [editingMed, setEditingMed]     = useState(null);
  const [editDays,   setEditDays]       = useState(['Mon']);
  const [editHour,   setEditHour]       = useState('08');
  const [editMin,    setEditMin]        = useState('00');
  const [editPeriod, setEditPeriod]     = useState('AM');
  const [isSaving,   setIsSaving]       = useState(false);
  const [showTimeModal, setShowTimeModal] = useState(false);

  // Temp state for time wheel picker
  const [tempHour,   setTempHour]   = useState('08');
  const [tempMin,    setTempMin]    = useState('00');
  const [tempPeriod, setTempPeriod] = useState('AM');

  const hourScrollRef   = useRef(null);
  const minuteScrollRef = useRef(null);
  const periodScrollRef = useRef(null);

  const isHelper      = user?.role === 'Guardian' || user?.role === 'CareGiver';
  const targetPatientId = isHelper ? user?.patient_id : user?.user_id;
  const patientLabel  = isHelper ? (user?.patient_name || 'Patient') : (user?.full_name || 'You');

  // Scroll the time wheels to the current value when the modal opens
  useEffect(() => {
    if (!showTimeModal) return;
    requestAnimationFrame(() => {
      const scrollTo = (ref, options, value) => {
        const idx = Math.max(options.indexOf(value), 0);
        ref.current?.scrollTo({y: idx * SLOT_ITEM_HEIGHT, animated: false});
      };
      scrollTo(hourScrollRef,   HOUR_OPTIONS,   tempHour);
      scrollTo(minuteScrollRef, MINUTE_OPTIONS, tempMin);
      scrollTo(periodScrollRef, PERIOD_OPTIONS, tempPeriod);
    });
  }, [showTimeModal]);

  const loadMedications = useCallback(async () => {
    if (!targetPatientId) return;
    setLoading(true);
    try {
      const data = await fetchPatientMedications(targetPatientId);
      setMedications(Array.isArray(data?.items) ? data.items : []);
    } catch {
      Alert.alert('Error', 'Could not load medications. Check your connection.');
    } finally {
      setLoading(false);
    }
  }, [targetPatientId]);

  useFocusEffect(useCallback(() => { loadMedications(); }, [loadMedications]));

  // ── Delete ────────────────────────────────────────────────────────────────
  const handleDelete = (med) => {
    Alert.alert(
      'Delete Medication',
      `Delete "${med.name}"? This permanently removes it and all its images.`,
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setDeletingId(med._id);
            try {
              await deleteMedication(med._id);
              setMedications((prev) => prev.filter((m) => m._id !== med._id));
            } catch (err) {
              Alert.alert('Error', err.message || 'Could not delete medication.');
            } finally {
              setDeletingId(null);
            }
          },
        },
      ],
    );
  };

  // ── Edit ──────────────────────────────────────────────────────────────────
  const handleEditPress = (med) => {
    const {days, hour, minute, period} = parseSchedule(med);
    setEditDays(days);
    setEditHour(hour);
    setEditMin(minute);
    setEditPeriod(period);
    setEditingMed(med);
  };

  const toggleEditDay = (day) => {
    setEditDays((prev) =>
      prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
    );
  };

  const openTimeModal = () => {
    setTempHour(editHour);
    setTempMin(editMin);
    setTempPeriod(editPeriod);
    setShowTimeModal(true);
  };

  const confirmTime = () => {
    setEditHour(tempHour);
    setEditMin(tempMin);
    setEditPeriod(tempPeriod);
    setShowTimeModal(false);
  };

  const handleSaveEdit = async () => {
    if (!editDays.length) {
      Alert.alert('Missing Days', 'Please select at least one day.');
      return;
    }

    const orig = parseSchedule(editingMed);
    const daysChanged =
      JSON.stringify([...editDays].sort()) !== JSON.stringify([...orig.days].sort());
    const timeChanged =
      editHour !== orig.hour || editMin !== orig.minute || editPeriod !== orig.period;

    if (!daysChanged && !timeChanged) {
      setEditingMed(null);
      return;
    }

    const partialSchedule = {};
    if (daysChanged) {
      partialSchedule.days = editDays;
    }
    if (timeChanged) {
      partialSchedule.time   = `${editHour}:${editMin} ${editPeriod}`;
      partialSchedule.hour   = editHour;
      partialSchedule.minute = editMin;
      partialSchedule.period = editPeriod;
    }

    setIsSaving(true);
    try {
      const res = await updateMedicationSchedule(editingMed._id, partialSchedule);
      const serverMed = res?.medication;
      setMedications((prev) =>
        prev.map((m) => {
          if (m._id !== editingMed._id) return m;
          if (serverMed) return serverMed;
          return {
            ...m,
            ...(daysChanged ? {date: editDays} : {}),
            ...(timeChanged ? {time: `${editHour}:${editMin} ${editPeriod}`} : {}),
            schedule: {
              ...(m.schedule && typeof m.schedule === 'object' ? m.schedule : {}),
              ...partialSchedule,
            },
          };
        }),
      );
      setEditingMed(null);
    } catch (err) {
      Alert.alert('Error', err.message || 'Could not save changes.');
    } finally {
      setIsSaving(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <ScreenBg>
      <TopBar
        navigation={navigation}
        title="My Medications"
        leftElement={
          <TouchableOpacity
            onPress={() => navigation.navigate('Dashboard')}
            activeOpacity={0.8}
            style={styles.backBtn}>
            <Text style={styles.backBtnText}>←</Text>
          </TouchableOpacity>
        }
      />

      <View style={styles.subHeader}>
        <Text style={styles.subHeaderText}>
          {isHelper ? `Medications for ${patientLabel}` : 'Your medication list'}
        </Text>
        {!loading && (
          <Text style={styles.countBadge}>{medications.length} total</Text>
        )}
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={COLORS.teal} />
          <Text style={styles.loadingText}>Loading medications...</Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}>
          {medications.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>💊</Text>
              <Text style={styles.emptyTitle}>No medications found</Text>
              <Text style={styles.emptySubtitle}>
                Add medications using the Add Meds option.
              </Text>
            </View>
          ) : (
            medications.map((med) => {
              const imageUrl  = getImageUrl(med.photo_url || (Array.isArray(med.photo_urls) ? med.photo_urls[0] : null));
              const isDeleting = deletingId === med._id;

              return (
                <View key={med._id} style={styles.medCard}>
                  <View style={styles.medImageWrapper}>
                    {imageUrl ? (
                      <Image source={{uri: imageUrl}} style={styles.medImage} resizeMode="cover" />
                    ) : (
                      <View style={styles.medImagePlaceholder}>
                        <Text style={styles.medImagePlaceholderIcon}>💊</Text>
                      </View>
                    )}
                  </View>

                  <View style={styles.medInfo}>
                    <Text style={styles.medName} numberOfLines={2}>{med.name}</Text>
                    <View style={styles.schedulePill}>
                      <Text style={styles.scheduleText} numberOfLines={2}>
                        {formatSchedule(med)}
                      </Text>
                    </View>
                    {med.description ? (
                      <Text style={styles.medDesc} numberOfLines={2}>{med.description}</Text>
                    ) : null}
                  </View>

                  <View style={styles.actionsCol}>
                    {/* Edit button — visible to everyone */}
                    <TouchableOpacity
                      style={styles.editBtn}
                      onPress={() => handleEditPress(med)}
                      activeOpacity={0.75}>
                      <Text style={styles.editBtnIcon}>✏️</Text>
                    </TouchableOpacity>

                    {/* Delete button — only for guardian / caregiver */}
                    {isHelper && (
                      <TouchableOpacity
                        style={[styles.deleteBtn, isDeleting && styles.deleteBtnDisabled]}
                        onPress={() => !isDeleting && handleDelete(med)}
                        activeOpacity={0.75}
                        disabled={isDeleting}>
                        {isDeleting ? (
                          <ActivityIndicator size="small" color="#fff" />
                        ) : (
                          <Text style={styles.deleteBtnIcon}>🗑</Text>
                        )}
                      </TouchableOpacity>
                    )}
                  </View>
                </View>
              );
            })
          )}
        </ScrollView>
      )}

      {/* ── Edit Schedule Modal ───────────────────────────────────────────── */}
      <Modal
        visible={!!editingMed}
        transparent
        animationType="slide"
        onRequestClose={() => setEditingMed(null)}>
        <View style={styles.modalOverlay}>
          <View style={styles.editSheet}>
            {/* Header */}
            <View style={styles.editHeader}>
              <Text style={styles.editTitle}>Edit Schedule</Text>
              <TouchableOpacity onPress={() => setEditingMed(null)} style={styles.editCloseBtn}>
                <Text style={styles.editCloseText}>✕</Text>
              </TouchableOpacity>
            </View>

            <Text style={styles.editMedName}>{editingMed?.name}</Text>

            {/* Days */}
            <Text style={styles.editSectionLabel}>Days</Text>
            <View style={styles.daysGrid}>
              {DAY_OPTIONS.map((day) => {
                const selected = editDays.includes(day);
                return (
                  <TouchableOpacity
                    key={day}
                    style={[styles.dayChip, selected && styles.dayChipActive]}
                    onPress={() => toggleEditDay(day)}
                    activeOpacity={0.75}>
                    <Text style={[styles.dayChipText, selected && styles.dayChipTextActive]}>
                      {day}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            {/* Time */}
            <Text style={styles.editSectionLabel}>Time</Text>
            <TouchableOpacity
              style={styles.timeDisplay}
              onPress={openTimeModal}
              activeOpacity={0.8}>
              <Text style={styles.timeDisplayText}>
                {editHour}:{editMin} {editPeriod}
              </Text>
              <Text style={styles.timeDisplayHint}>Tap to change</Text>
            </TouchableOpacity>

            {/* Save */}
            <TouchableOpacity
              style={[styles.saveBtn, isSaving && styles.saveBtnDisabled]}
              onPress={handleSaveEdit}
              activeOpacity={0.8}
              disabled={isSaving}>
              {isSaving ? (
                <ActivityIndicator color={COLORS.white} />
              ) : (
                <Text style={styles.saveBtnText}>Save Changes</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* ── Time Wheel Modal ──────────────────────────────────────────────── */}
      <Modal
        visible={showTimeModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowTimeModal(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.timeModalCard}>
            <View style={styles.timeModalHeader}>
              <TouchableOpacity onPress={() => setShowTimeModal(false)}>
                <Text style={styles.timeModalAction}>Cancel</Text>
              </TouchableOpacity>
              <Text style={styles.timeModalTitle}>Pick Time</Text>
              <TouchableOpacity onPress={confirmTime}>
                <Text style={styles.timeModalAction}>Done</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.wheelsRow}>
              {/* Hour */}
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
                    onMomentumScrollEnd={(e) =>
                      setTempHour(getOptionFromOffset(e.nativeEvent.contentOffset.y, HOUR_OPTIONS))
                    }
                    onScrollEndDrag={(e) =>
                      setTempHour(getOptionFromOffset(e.nativeEvent.contentOffset.y, HOUR_OPTIONS))
                    }>
                    {HOUR_OPTIONS.map((opt) => (
                      <View key={opt} style={styles.wheelItem}>
                        <Text style={[styles.wheelItemText, tempHour === opt && styles.wheelItemTextSelected]}>
                          {opt}
                        </Text>
                      </View>
                    ))}
                  </ScrollView>
                </View>
              </View>

              {/* Minute */}
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
                    onMomentumScrollEnd={(e) =>
                      setTempMin(getOptionFromOffset(e.nativeEvent.contentOffset.y, MINUTE_OPTIONS))
                    }
                    onScrollEndDrag={(e) =>
                      setTempMin(getOptionFromOffset(e.nativeEvent.contentOffset.y, MINUTE_OPTIONS))
                    }>
                    {MINUTE_OPTIONS.map((opt) => (
                      <View key={opt} style={styles.wheelItem}>
                        <Text style={[styles.wheelItemText, tempMin === opt && styles.wheelItemTextSelected]}>
                          {opt}
                        </Text>
                      </View>
                    ))}
                  </ScrollView>
                </View>
              </View>

              {/* AM / PM */}
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
                    onMomentumScrollEnd={(e) =>
                      setTempPeriod(getOptionFromOffset(e.nativeEvent.contentOffset.y, PERIOD_OPTIONS))
                    }
                    onScrollEndDrag={(e) =>
                      setTempPeriod(getOptionFromOffset(e.nativeEvent.contentOffset.y, PERIOD_OPTIONS))
                    }>
                    {PERIOD_OPTIONS.map((opt) => (
                      <View key={opt} style={styles.wheelItem}>
                        <Text style={[styles.wheelItemText, tempPeriod === opt && styles.wheelItemTextSelected]}>
                          {opt}
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
  subHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: 18,
    marginTop: 6,
    marginBottom: 10,
  },
  subHeaderText: {
    fontSize: 13,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.55)',
    flex: 1,
  },
  countBadge: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.teal,
    backgroundColor: 'rgba(126,207,212,0.15)',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 12,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  loadingText: {
    fontSize: 14,
    color: 'rgba(255,255,255,0.5)',
    fontWeight: '300',
  },
  listContent: {
    paddingHorizontal: 18,
    paddingBottom: Platform.OS === 'ios' ? 50 : 32,
    gap: 12,
  },
  emptyState: {marginTop: 60, alignItems: 'center', gap: 8},
  emptyIcon:  {fontSize: 48},
  emptyTitle: {fontSize: 18, fontWeight: '600', color: COLORS.white, marginTop: 8},
  emptySubtitle: {
    fontSize: 13, fontWeight: '300',
    color: 'rgba(255,255,255,0.5)',
    textAlign: 'center', paddingHorizontal: 24,
  },
  medCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 18,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    padding: 12,
    gap: 12,
  },
  medImageWrapper: {
    width: 76, height: 76,
    borderRadius: 14, overflow: 'hidden', flexShrink: 0,
  },
  medImage: {width: '100%', height: '100%'},
  medImagePlaceholder: {
    width: '100%', height: '100%',
    backgroundColor: 'rgba(126,207,212,0.15)',
    alignItems: 'center', justifyContent: 'center',
  },
  medImagePlaceholderIcon: {fontSize: 30},
  medInfo: {flex: 1, gap: 6},
  medName: {fontSize: 15, fontWeight: '700', color: COLORS.white, lineHeight: 20},
  schedulePill: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(126,207,212,0.2)',
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  scheduleText: {fontSize: 11, fontWeight: '600', color: COLORS.teal, lineHeight: 16},
  medDesc: {
    fontSize: 12, fontWeight: '300',
    color: 'rgba(255,255,255,0.55)', lineHeight: 17,
  },
  actionsCol: {gap: 8, flexShrink: 0, alignItems: 'center'},
  editBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(126,207,212,0.2)',
    alignItems: 'center', justifyContent: 'center',
  },
  editBtnIcon: {fontSize: 18},
  deleteBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(231,76,60,0.25)',
    alignItems: 'center', justifyContent: 'center',
  },
  deleteBtnDisabled: {backgroundColor: 'rgba(231,76,60,0.12)'},
  deleteBtnIcon: {fontSize: 18},
  backBtn: {
    width: 34, height: 34, borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center', justifyContent: 'center',
  },
  backBtnText: {color: COLORS.white, fontSize: 18, fontWeight: '700', lineHeight: 22},

  // ── Edit modal ────────────────────────────────────────────────────────────
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'flex-end',
  },
  editSheet: {
    backgroundColor: '#17181E',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    paddingHorizontal: 20,
    paddingBottom: Platform.OS === 'ios' ? 40 : 24,
    paddingTop: 8,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
  },
  editHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.07)',
    marginBottom: 14,
  },
  editTitle: {fontSize: 17, fontWeight: '700', color: COLORS.white},
  editCloseBtn: {
    width: 30, height: 30, borderRadius: 15,
    backgroundColor: 'rgba(255,255,255,0.1)',
    alignItems: 'center', justifyContent: 'center',
  },
  editCloseText: {color: COLORS.white, fontSize: 14, fontWeight: '700'},
  editMedName: {
    fontSize: 14, fontWeight: '400',
    color: 'rgba(255,255,255,0.5)',
    marginBottom: 18,
  },
  editSectionLabel: {
    fontSize: 13, fontWeight: '600',
    color: 'rgba(255,255,255,0.7)',
    marginBottom: 10,
  },
  daysGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 20,
  },
  dayChip: {
    paddingHorizontal: 14, paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  dayChipActive: {
    backgroundColor: 'rgba(126,207,212,0.2)',
    borderColor: COLORS.teal,
  },
  dayChipText: {fontSize: 13, fontWeight: '600', color: 'rgba(255,255,255,0.45)'},
  dayChipTextActive: {color: COLORS.teal},
  timeDisplay: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 24,
  },
  timeDisplayText: {fontSize: 22, fontWeight: '700', color: COLORS.white},
  timeDisplayHint: {fontSize: 11, color: 'rgba(255,255,255,0.4)'},
  saveBtn: {
    backgroundColor: COLORS.teal,
    borderRadius: 14,
    paddingVertical: 15,
    alignItems: 'center',
  },
  saveBtnDisabled: {opacity: 0.5},
  saveBtnText: {fontSize: 16, fontWeight: '700', color: COLORS.bgDark},

  // ── Time wheel modal ──────────────────────────────────────────────────────
  timeModalCard: {
    backgroundColor: '#17181E',
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.08)',
    marginHorizontal: 12,
  },
  timeModalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 14, paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255,255,255,0.06)',
  },
  timeModalAction: {color: COLORS.teal, fontSize: 15, fontWeight: '600'},
  timeModalTitle:  {color: COLORS.white, fontSize: 15, fontWeight: '600'},
  wheelsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
    paddingHorizontal: 12,
    paddingTop: 14,
    paddingBottom: 16,
  },
  wheelCol: {flex: 1},
  wheelColPeriod: {width: 84},
  wheelTitle: {
    color: 'rgba(255,255,255,0.72)',
    fontSize: 11, marginBottom: 6, textAlign: 'center',
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
    left: 8, right: 8,
    top: SLOT_CENTER_OFFSET,
    height: SLOT_ITEM_HEIGHT,
    backgroundColor: 'rgba(255,255,255,0.08)',
    borderRadius: 8,
    zIndex: 2,
  },
  wheelContent: {paddingVertical: SLOT_CENTER_OFFSET},
  wheelItem: {height: SLOT_ITEM_HEIGHT, justifyContent: 'center', alignItems: 'center'},
  wheelItemText: {
    color: 'rgba(255,255,255,0.38)',
    fontSize: 21, fontWeight: '500',
  },
  wheelItemTextSelected: {color: COLORS.white, fontWeight: '700'},
});
