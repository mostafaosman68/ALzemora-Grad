import React, {useState, useCallback} from 'react';
import {
  View,
  Text,
  ScrollView,
  Image,
  StyleSheet,
  Alert,
  ActivityIndicator,
  Platform,
} from 'react-native';
import {TouchableOpacity} from 'react-native';
import {useFocusEffect} from '@react-navigation/native';
import {ScreenBg, TopBar, COLORS} from '../components/UI';
import {useAuth} from '../../App';
import {BASE_URL} from '../config';

const RELATION_COLORS = {
  son:       '#4CAF50',
  daughter:  '#E91E63',
  wife:      '#9C27B0',
  husband:   '#3F51B5',
  brother:   '#2196F3',
  sister:    '#FF9800',
  father:    '#795548',
  mother:    '#F44336',
  friend:    '#00BCD4',
  caregiver: '#607D8B',
  doctor:    '#009688',
};

const getRelationColor = (relation) => {
  if (!relation) return COLORS.teal;
  return RELATION_COLORS[relation.toLowerCase()] || COLORS.teal;
};

const getImageUrl = (photoPath) => {
  if (!photoPath) return null;
  const marker = '/data/';
  const idx = photoPath.indexOf(marker);
  if (idx === -1) return null;
  return `${BASE_URL}${photoPath.substring(idx)}`;
};

export default function PeopleListScreen({navigation}) {
  const {user} = useAuth();
  const [people, setPeople] = useState([]);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState(null);

  const isHelper = user?.role === 'Guardian' || user?.role === 'CareGiver';
  const targetPatientId = isHelper ? user?.patient_id : user?.user_id;
  const patientLabel = isHelper ? (user?.patient_name || 'Patient') : (user?.full_name || 'You');

  const loadPeople = useCallback(async () => {
    if (!targetPatientId) return;
    setLoading(true);
    try {
      const response = await fetch(
        `${BASE_URL}/people/${encodeURIComponent(targetPatientId)}?include_embeddings=false`,
        {method: 'GET', headers: {Accept: 'application/json'}},
      );
      const data = await response.json();
      if (!response.ok || data?.error) {
        throw new Error(data?.error || 'Failed to load people');
      }
      setPeople(Array.isArray(data?.people) ? data.people : []);
    } catch (err) {
      Alert.alert('Error', 'Could not load contacts. Check your connection.');
    } finally {
      setLoading(false);
    }
  }, [targetPatientId]);

  useFocusEffect(
    useCallback(() => {
      loadPeople();
    }, [loadPeople]),
  );

  const handleDelete = (person) => {
    Alert.alert(
      'Delete Contact',
      `Delete "${person.name}"? This will permanently remove their face, voice, and all associated data.`,
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            setDeletingId(person._id);
            try {
              const response = await fetch(
                `${BASE_URL}/people/${encodeURIComponent(person._id)}`,
                {method: 'DELETE', headers: {Accept: 'application/json'}},
              );
              const data = await response.json();
              if (!response.ok || data?.error) {
                throw new Error(data?.error || data?.detail || 'Delete failed');
              }
              setPeople((prev) => prev.filter((p) => p._id !== person._id));
            } catch (err) {
              Alert.alert('Error', err.message || 'Could not delete contact.');
            } finally {
              setDeletingId(null);
            }
          },
        },
      ],
    );
  };

  return (
    <ScreenBg>
      <TopBar
        navigation={navigation}
        title="Registered Faces"
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
          {isHelper ? `People registered for ${patientLabel}` : 'Your registered contacts'}
        </Text>
        {!loading && (
          <Text style={styles.countBadge}>{people.length} total</Text>
        )}
      </View>

      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={COLORS.teal} />
          <Text style={styles.loadingText}>Loading contacts...</Text>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={styles.listContent}
          showsVerticalScrollIndicator={false}>
          {people.length === 0 ? (
            <View style={styles.emptyState}>
              <Text style={styles.emptyIcon}>👥</Text>
              <Text style={styles.emptyTitle}>No contacts registered</Text>
              <Text style={styles.emptySubtitle}>
                Add family members or friends using the Add Friends option.
              </Text>
            </View>
          ) : (
            people.map((person) => {
              const imageUrl = getImageUrl(person.photo_url);
              const relationColor = getRelationColor(person.relation);

              const isDeleting = deletingId === person._id;

              return (
                <View key={person._id} style={styles.personCard}>
                  <View style={styles.avatarWrapper}>
                    {imageUrl ? (
                      <Image
                        source={{uri: imageUrl}}
                        style={styles.avatar}
                        resizeMode="cover"
                      />
                    ) : (
                      <View style={[styles.avatarPlaceholder, {borderColor: relationColor}]}>
                        <Text style={styles.avatarInitial}>
                          {(person.name || '?')[0].toUpperCase()}
                        </Text>
                      </View>
                    )}
                    {person.has_voice && (
                      <View style={styles.voiceBadge}>
                        <Text style={styles.voiceBadgeIcon}>🎙</Text>
                      </View>
                    )}
                  </View>

                  <View style={styles.personInfo}>
                    <Text style={styles.personName}>{person.name}</Text>
                    {person.relation ? (
                      <View style={[styles.relationPill, {backgroundColor: `${relationColor}30`}]}>
                        <Text style={[styles.relationText, {color: relationColor}]}>
                          {person.relation}
                        </Text>
                      </View>
                    ) : (
                      <Text style={styles.noRelation}>No relation set</Text>
                    )}
                  </View>

                  {isHelper && (
                    <TouchableOpacity
                      style={[styles.deleteBtn, isDeleting && styles.deleteBtnDisabled]}
                      onPress={() => !isDeleting && handleDelete(person)}
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
              );
            })
          )}
        </ScrollView>
      )}
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
  emptyState: {
    marginTop: 60,
    alignItems: 'center',
    gap: 8,
  },
  emptyIcon: {
    fontSize: 48,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: COLORS.white,
    marginTop: 8,
  },
  emptySubtitle: {
    fontSize: 13,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.5)',
    textAlign: 'center',
    paddingHorizontal: 24,
  },
  personCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.07)',
    borderRadius: 18,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    padding: 14,
    gap: 14,
  },
  avatarWrapper: {
    position: 'relative',
    flexShrink: 0,
  },
  avatar: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.2)',
  },
  avatarPlaceholder: {
    width: 72,
    height: 72,
    borderRadius: 36,
    borderWidth: 2,
    backgroundColor: 'rgba(255,255,255,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarInitial: {
    fontSize: 28,
    fontWeight: '700',
    color: COLORS.white,
  },
  voiceBadge: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: COLORS.bgDark,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.15)',
  },
  voiceBadgeIcon: {
    fontSize: 12,
  },
  personInfo: {
    flex: 1,
    gap: 8,
  },
  personName: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.white,
  },
  relationPill: {
    alignSelf: 'flex-start',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 4,
  },
  relationText: {
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
  noRelation: {
    fontSize: 12,
    fontWeight: '300',
    color: 'rgba(255,255,255,0.35)',
    fontStyle: 'italic',
  },
  deleteBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(231,76,60,0.25)',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  deleteBtnDisabled: {
    backgroundColor: 'rgba(231,76,60,0.12)',
  },
  deleteBtnIcon: {
    fontSize: 18,
  },
  backBtn: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  backBtnText: {
    color: COLORS.white,
    fontSize: 18,
    fontWeight: '700',
    lineHeight: 22,
  },
});
