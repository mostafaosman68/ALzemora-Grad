import React, {useState, useEffect} from 'react';
import {
  View,
  Text,
  ScrollView,
  Image,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Platform,
  ActivityIndicator,
  Alert,
} from 'react-native';
import {ScreenBg, TopBar, COLORS, logo} from '../components/UI';
import {useAuth} from '../../App';
import {usePermissions} from '../hooks/usePermissions';
import { BASE_URL } from '../config';

function StatusBadge() {
  return (
    <View style={styles.statusBadge}>
      <View style={styles.statusDot} />
      <Text style={styles.statusText}>Active (Awake)</Text>
    </View>
  );
}

export default function UserProfileScreen({navigation}) {
  const {user, logout, setUser} = useAuth();
  const {canEdit} = usePermissions();
  const [patientData, setPatientData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);
  const [profileForm, setProfileForm] = useState({
    full_name: '',
    age: '',
    address: '',
    emergency_contact: '',
    dnr_status: false,
  });

  const getAccountLabel = (role) => {
    if (role === 'Guardian') return 'Guardian Account';
    if (role === 'CareGiver') return 'Caregiver Account';
    return 'Patient Account';
  };

  useEffect(() => {
    if (canEdit) {
      if (user?.patient_name) {
        fetchPatientData();
      } else {
        Alert.alert('Profile Error', 'No patient linked to this account. Please contact support.');
      }
    }
  }, [user?.patient_name, canEdit]);

  const fetchPatientData = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${BASE_URL}/users/get-user-by-name?name=${encodeURIComponent(user.patient_name)}`);
      const data = await response.json();
      if (data && !data.error) {
        setPatientData(data);
      } else {
        const errMsg = data?.error || 'Patient not found';
        console.error('Error fetching patient data:', errMsg);
        Alert.alert('Error', `Could not load patient profile: ${errMsg}`);
      }
    } catch (err) {
      console.error('Error fetching patient data:', err);
      Alert.alert('Connection Error', 'Could not reach the server. Please check your network and try again.');
    } finally {
      setLoading(false);
    }
  };

  // Determine which data to display
  const displayData = canEdit && patientData ? patientData : user;
  const isEditingPatientProfile = canEdit && patientData;
  const editTargetRole = isEditingPatientProfile ? 'User' : user?.role;
  const editTargetUserId = isEditingPatientProfile ? patientData?.user_id : user?.user_id;

  useEffect(() => {
    if (displayData) {
      setProfileForm({
        full_name: displayData.full_name ?? '',
        age: displayData.age ? String(displayData.age) : '',
        address: displayData.address ?? '',
        emergency_contact: displayData.emergency_contact ?? '',
        dnr_status: Boolean(displayData.dnr_status),
      });
    }
  }, [displayData]);

  const handleSaveProfile = async () => {
    if (!canEdit) {
      Alert.alert('Permission Denied', 'Patient accounts cannot edit profiles.');
      return;
    }
    if (!editTargetUserId || !editTargetRole) {
      Alert.alert('Update Error', 'Could not determine which profile to update. Please try again.');
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${BASE_URL}/users/update-user`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_id: user?.user_id,
          role: editTargetRole,
          editor_role: user?.role,
          patient_user_id: editTargetUserId,
          full_name: profileForm.full_name,
          age: profileForm.age ? Number(profileForm.age) : null,
          address: profileForm.address,
          emergency_contact: profileForm.emergency_contact,
          dnr_status: profileForm.dnr_status,
        }),
      });

      const data = await response.json();
      if (!response.ok || data.error) {
        Alert.alert('Update Failed', data.error || 'Could not update profile');
        return;
      }

      const updatedUser = data.user;
      if (isEditingPatientProfile) {
        setPatientData((prev) => ({...prev, ...updatedUser}));
      } else {
        setUser((prev) => ({...prev, ...updatedUser}));
      }

      Alert.alert('Success', 'Profile updated successfully');
      setEditing(false);
    } catch (err) {
      console.error('Error saving profile:', err);
      Alert.alert('Error', 'Failed to save profile. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const profileFields = [
    {label: 'Name', value: displayData?.full_name ?? 'User', icon: '👤'},
    {label: 'Age', value: displayData?.age ? String(displayData.age) : 'N/A', icon: '🎂'},
    {label: 'Status', value: null, isStatus: true, icon: '💚'},
    {label: 'Address', value: displayData?.address ?? 'N/A', icon: '🏠'},
    {
      label: 'Emergency contacts',
      value: displayData?.emergency_contact ?? 'N/A',
      icon: '📞',
    },
    {label: 'DNR Status', value: displayData?.dnr_status ? 'Yes' : 'No', icon: '📋'},
  ];

  const editableFields = [
    {key: 'full_name', label: 'Name', icon: '👤', placeholder: 'Full name'},
    {key: 'age', label: 'Age', icon: '🎂', placeholder: 'Age', keyboardType: 'numeric'},
    {key: 'address', label: 'Address', icon: '🏠', placeholder: 'Address'},
    {key: 'emergency_contact', label: 'Emergency contacts', icon: '📞', placeholder: 'Emergency contacts'},
    {key: 'dnr_status', label: 'DNR Status', icon: '📋', placeholder: 'Yes / No'},
  ];

  return (
    <ScreenBg>
      <TopBar navigation={navigation} title="User Profile" />

      <View style={styles.card}>
        <ScrollView
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.scroll}>

          {loading ? (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={COLORS.dark} />
              <Text style={styles.loadingText}>Loading profile...</Text>
            </View>
          ) : (
            <>
              <View style={styles.avatarRow}>
                <Image
                  source={logo}
                  style={styles.avatar}
                  resizeMode="contain"
                />
                <View style={styles.avatarInfo}>
                  <Text style={styles.avatarName}>{displayData?.full_name ?? 'User'}</Text>
                  <Text style={styles.avatarRole}>
                    Alzheimer's Patient · {canEdit && patientData ? 'Patient Account' : getAccountLabel(user?.role)}
                  </Text>
                </View>
              </View>

              {editing ? (
                editableFields.map(({key, label, icon, placeholder, keyboardType}) => (
                  <View key={key} style={styles.field}>
                    <Text style={styles.fieldIcon}>{icon}</Text>
                    <View style={styles.fieldContent}>
                      <Text style={styles.fieldLabel}>{label}</Text>
                      <TextInput
                        value={key === 'dnr_status'
                          ? profileForm.dnr_status ? 'Yes' : 'No'
                          : profileForm[key]}
                        placeholder={placeholder}
                        placeholderTextColor="rgba(0,0,0,0.35)"
                        keyboardType={keyboardType || 'default'}
                        style={styles.input}
                        onChangeText={(text) => {
                          if (key === 'dnr_status') {
                            setProfileForm((prev) => ({
                              ...prev,
                              dnr_status: text.trim().toLowerCase().startsWith('y'),
                            }));
                          } else {
                            setProfileForm((prev) => ({...prev, [key]: text}));
                          }
                        }}
                      />
                    </View>
                  </View>
                ))
              ) : (
                profileFields.map(({label, value, isStatus, icon}) => (
                  <View key={label} style={styles.field}>
                    <Text style={styles.fieldIcon}>{icon}</Text>
                    <View style={styles.fieldContent}>
                      <Text style={styles.fieldLabel}>{label}</Text>
                      {isStatus ? (
                        <StatusBadge />
                      ) : (
                        <Text style={styles.fieldValue}>{value}</Text>
                      )}
                    </View>
                  </View>
                ))
              )}

              <View style={styles.actionRow}>
                <TouchableOpacity
                  style={styles.actionBtn}
                  onPress={() => navigation.navigate('Dashboard')}>
                  <Text style={styles.actionBtnText}>← Dashboard</Text>
                </TouchableOpacity>

                {canEdit && (
                  <TouchableOpacity
                    style={styles.actionBtn}
                    onPress={editing ? handleSaveProfile : () => setEditing(true)}>
                    <Text style={styles.actionBtnText}>{editing ? 'Save Profile' : 'Edit Profile'}</Text>
                  </TouchableOpacity>
                )}

                <TouchableOpacity
                  style={styles.logoutBtn}
                  onPress={async () => {
                    if (editing) {
                      setEditing(false);
                      setProfileForm({
                        full_name: displayData?.full_name ?? '',
                        age: displayData?.age ? String(displayData.age) : '',
                        address: displayData?.address ?? '',
                        emergency_contact: displayData?.emergency_contact ?? '',
                        dnr_status: Boolean(displayData?.dnr_status),
                      });
                      return;
                    }
                    await logout();
                    navigation.reset({
                      index: 0,
                      routes: [{ name: 'Splash' }],
                    });
                  }}>
                  <Text style={styles.logoutBtnText}>{editing ? 'Cancel' : '🚪 Logout'}</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
        </ScrollView>
      </View>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  card: {
    position: 'absolute',
    top: Platform.OS === 'ios' ? 140 : 128,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: COLORS.card,
    borderTopLeftRadius: 50,
    borderTopRightRadius: 50,
    overflow: 'hidden',
  },
  scroll: {
    padding: 24,
    paddingBottom: Platform.OS === 'ios' ? 50 : 30,
  },

  loadingContainer: {
    justifyContent: 'center',
    alignItems: 'center',
    height: 300,
    gap: 12,
  },
  loadingText: {
    fontSize: 14,
    color: COLORS.text,
    marginTop: 8,
  },

  avatarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    marginBottom: 20,
    paddingBottom: 18,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.1)',
  },
  avatar: {
    width: 70,
    height: 70,
    borderRadius: 35,
    borderWidth: 3,
    borderColor: '#2a4a5c',
    backgroundColor: 'rgba(42,74,92,0.12)',
    padding: 6,
  },
  avatarInfo: {gap: 3},
  avatarName: {
    fontSize: 20,
    fontWeight: '700',
    color: COLORS.text,
  },
  avatarRole: {
    fontSize: 12,
    fontWeight: '300',
    color: COLORS.subtext,
  },

  field: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.08)',
  },
  fieldIcon: {fontSize: 20, marginTop: 1},
  fieldContent: {flex: 1, gap: 2},
  fieldLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.subtext,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  fieldValue: {
    fontSize: 16,
    fontWeight: '400',
    color: COLORS.text,
  },
  input: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.12)',
    backgroundColor: '#fff',
    color: COLORS.text,
    fontSize: 16,
    minHeight: 44,
  },

  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#d4edda',
    borderRadius: 20,
    paddingHorizontal: 10,
    paddingVertical: 4,
    alignSelf: 'flex-start',
    marginTop: 2,
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#28a745',
  },
  statusText: {
    fontSize: 13,
    fontWeight: '500',
    color: '#155724',
  },

  actionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
    marginTop: 22,
  },
  actionBtn: {
    flex: 1,
    height: 46,
    borderRadius: 23,
    borderWidth: 2,
    borderColor: '#2a4a5c',
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionBtnText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#2a4a5c',
  },
  logoutBtn: {
    flex: 1,
    height: 46,
    borderRadius: 23,
    borderWidth: 2,
    borderColor: '#dc3545',
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoutBtnText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#dc3545',
  },
});