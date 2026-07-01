import React, {useState, useEffect, useRef, useCallback} from 'react';
import {
  View,
  Text,
  StyleSheet,
  Dimensions,
  Platform,
  ActivityIndicator,
  Alert,
  TouchableOpacity,
} from 'react-native';
import WebView from 'react-native-webview';
import {ScreenBg, TopBar, DarkBtn, BackBtn, COLORS} from '../components/UI';
import {BASE_URL} from '../config';
import {useAuth} from '../../App';

const {width, height} = Dimensions.get('window');
const MAP_H = height * 0.50;
const POLL_INTERVAL_MS = 30_000;

// ── Map HTML builders ──────────────────────────────────────────────────────

function buildViewHtml(lat, lon, city, country, isManual) {
  const label = [city, country].filter(Boolean).join(', ').replace(/'/g, "\\'");
  const badge = isManual
    ? '<div style="position:absolute;top:10px;left:10px;z-index:999;background:rgba(16,185,129,0.9);color:#fff;font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;font-family:sans-serif">📌 Pinned</div>'
    : '<div style="position:absolute;top:10px;left:10px;z-index:999;background:rgba(239,68,68,0.9);color:#fff;font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;font-family:sans-serif">⚠️ IP Estimate</div>';

  return `<!DOCTYPE html><html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"><\/script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}body{background:#0f172a}
  #map{width:100vw;height:100vh;position:relative}
  .leaflet-popup-content-wrapper{background:#1e293b;color:#f1f5f9;border-radius:12px;border:1px solid rgba(255,255,255,0.1)}
  .leaflet-popup-tip{background:#1e293b}
  .leaflet-popup-content{margin:10px 14px;font-size:13px;line-height:1.6}
  .pt{font-weight:700;font-size:14px;color:#60a5fa;margin-bottom:3px}
  .ps{color:#94a3b8;font-size:11px}
</style>
</head>
<body>
<div id="map">${badge}</div>
<script>
  var map=L.map('map',{zoomControl:true}).setView([${lat},${lon}],18);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
    attribution:'&copy; OpenStreetMap',maxZoom:19
  }).addTo(map);

  // 30 m geofence ring
  L.circle([${lat},${lon}],{
    radius:30,
    color:'#3b82f6',
    weight:2,
    opacity:0.9,
    fillColor:'#3b82f6',
    fillOpacity:0.10,
    dashArray:'6,4'
  }).addTo(map).bindTooltip('30 m radius',{permanent:false,direction:'top'});

  var icon=L.divIcon({
    html:'<div style="position:relative;width:26px;height:26px">'
        +'<div style="position:absolute;inset:0;background:rgba(59,130,246,0.25);border-radius:50%;animation:p 1.8s ease-out infinite"></div>'
        +'<div style="position:absolute;inset:4px;background:#3b82f6;border-radius:50%;border:3px solid #fff;box-shadow:0 0 12px rgba(59,130,246,0.9)"></div>'
        +'</div><style>@keyframes p{0%{transform:scale(1);opacity:.9}100%{transform:scale(2.5);opacity:0}}<\/style>',
    iconSize:[26,26],iconAnchor:[13,13],className:''
  });
  L.marker([${lat},${lon}],{icon}).addTo(map)
    .bindPopup('<div class="pt">Raspberry Pi 5</div><div class="ps">${label}</div><div class="ps">${lat.toFixed(5)}, ${lon.toFixed(5)}</div>')
    .openPopup();
<\/script>
</body></html>`;
}

function buildFixHtml(lat, lon) {
  return `<!DOCTYPE html><html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"><\/script>
<style>
  *{margin:0;padding:0;box-sizing:border-box}body{background:#0f172a}
  #map{width:100vw;height:100vh}
  #hint{position:absolute;top:10px;left:50%;transform:translateX(-50%);z-index:999;
    background:rgba(245,158,11,0.95);color:#fff;font-size:12px;font-weight:700;
    padding:7px 16px;border-radius:20px;font-family:sans-serif;white-space:nowrap;
    box-shadow:0 2px 8px rgba(0,0,0,0.4);pointer-events:none}
</style>
</head>
<body>
<div id="map"><div id="hint">👆 Tap the map to pin the Pi's real location</div></div>
<script>
  var map=L.map('map',{zoomControl:true}).setView([${lat},${lon}],18);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
    attribution:'&copy; OpenStreetMap',maxZoom:19
  }).addTo(map);
  var marker=null;
  var pinIcon=L.divIcon({
    html:'<div style="width:22px;height:22px;background:#f59e0b;border-radius:50%;border:3px solid #fff;box-shadow:0 0 10px rgba(245,158,11,0.8)"></div>',
    iconSize:[22,22],iconAnchor:[11,11],className:''
  });
  map.on('click',function(e){
    if(marker) map.removeLayer(marker);
    marker=L.marker(e.latlng,{icon:pinIcon}).addTo(map);
    marker.bindPopup('<b>New Pi location</b><br>'+e.latlng.lat.toFixed(5)+', '+e.latlng.lng.toFixed(5)).openPopup();
    window.ReactNativeWebView.postMessage(JSON.stringify({lat:e.latlng.lat,lon:e.latlng.lng}));
  });
<\/script>
</body></html>`;
}

// ── Screen ─────────────────────────────────────────────────────────────────

export default function GeoLocationScreen({navigation}) {
  const {user} = useAuth();
  const isHelper = user?.role === 'Guardian' || user?.role === 'CareGiver';

  const [tracking, setTracking]   = useState(false);
  const [fixMode, setFixMode]     = useState(false);
  const [pendingPin, setPendingPin] = useState(null); // {lat, lon} tapped but not saved yet
  const [location, setLocation]   = useState(null);
  const [loading, setLoading]     = useState(false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState(null);
  const intervalRef               = useRef(null);

  const fetchLocation = useCallback(async () => {
    try {
      setError(null);
      const resp = await fetch(`${BASE_URL}/gps/location`, {
        headers: {Accept: 'application/json'},
      });
      if (!resp.ok) throw new Error(`Server error ${resp.status}`);
      const data = await resp.json();
      setLocation(data);
    } catch (err) {
      setError(err.message || 'Could not reach Pi');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isHelper) return;
    setLoading(true);
    fetchLocation();
  }, [isHelper, fetchLocation]);

  useEffect(() => {
    if (tracking && isHelper && !fixMode) {
      intervalRef.current = setInterval(fetchLocation, POLL_INTERVAL_MS);
    } else {
      clearInterval(intervalRef.current);
    }
    return () => clearInterval(intervalRef.current);
  }, [tracking, isHelper, fixMode, fetchLocation]);

  // Called when user taps the map in fix mode
  const handleMapMessage = useCallback((event) => {
    try {
      const {lat, lon} = JSON.parse(event.nativeEvent.data);
      setPendingPin({lat, lon});
    } catch (_) {}
  }, []);

  const savePin = async () => {
    if (!pendingPin) return;
    setSaving(true);
    try {
      const resp = await fetch(`${BASE_URL}/gps/set`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', Accept: 'application/json'},
        body: JSON.stringify({lat: pendingPin.lat, lon: pendingPin.lon, city: '', region: '', country: ''}),
      });
      if (!resp.ok) throw new Error('Save failed');
      setFixMode(false);
      setPendingPin(null);
      setLoading(true);
      fetchLocation();
      Alert.alert('Location Saved', 'The Pi\'s real location has been pinned on the map.');
    } catch (err) {
      Alert.alert('Error', err.message || 'Could not save location');
    } finally {
      setSaving(false);
    }
  };

  const clearPin = () => {
    Alert.alert(
      'Reset Location',
      'This will remove the manual pin and revert to IP estimation. Continue?',
      [
        {text: 'Cancel', style: 'cancel'},
        {
          text: 'Reset',
          style: 'destructive',
          onPress: async () => {
            await fetch(`${BASE_URL}/gps/set`, {method: 'DELETE'});
            setLoading(true);
            fetchLocation();
          },
        },
      ],
    );
  };

  // ── Access denied for patients ───────────────────────────────────────────
  if (!isHelper) {
    return (
      <ScreenBg>
        <TopBar navigation={navigation} />
        <View style={styles.deniedContainer}>
          <Text style={styles.deniedIcon}>🔒</Text>
          <Text style={styles.deniedTitle}>Restricted Access</Text>
          <Text style={styles.deniedSub}>
            Pi location tracking is only available to Guardians and Caregivers.
          </Text>
          <BackBtn onPress={() => navigation.navigate('Dashboard')} label="← Back to Dashboard" />
        </View>
      </ScreenBg>
    );
  }

  const locationLabel =
    location
      ? [location.city, location.region, location.country].filter(Boolean).join(', ') || 'Pinned location'
      : '—';

  const isManual = location?.source === 'manual';
  const mapCenter = pendingPin ?? location ?? {lat: 31.2018, lon: 29.9158};

  const viewHtml = location
    ? buildViewHtml(location.lat, location.lon, location.city, location.country, isManual)
    : null;

  const fixHtml = buildFixHtml(mapCenter.lat, mapCenter.lon);

  return (
    <ScreenBg>
      <TopBar navigation={navigation} />

      {/* Header */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>GEO-Location</Text>
          <Text style={styles.headerSub}>
            {fixMode ? 'Tap the map to set the real location' : `Monitoring Pi for ${user?.patient_name || 'Patient'}`}
          </Text>
        </View>
        <View style={[styles.roleBadge, user?.role === 'Guardian' ? styles.guardianBadge : styles.caregiverBadge]}>
          <Text style={styles.roleBadgeText}>{user?.role}</Text>
        </View>
      </View>

      {/* Map */}
      <View style={styles.mapContainer}>
        {loading && !location ? (
          <View style={styles.mapPlaceholder}>
            <ActivityIndicator size="large" color="#3b82f6" />
            <Text style={styles.placeholderText}>Locating Pi…</Text>
          </View>
        ) : error && !location ? (
          <View style={styles.mapPlaceholder}>
            <Text style={styles.errorText}>Could not locate Pi</Text>
            <Text style={styles.errorSub}>{error}</Text>
          </View>
        ) : fixMode ? (
          <WebView
            source={{html: fixHtml}}
            style={styles.map}
            javaScriptEnabled
            domStorageEnabled
            originWhitelist={['*']}
            onMessage={handleMapMessage}
          />
        ) : viewHtml ? (
          <WebView
            source={{html: viewHtml}}
            style={styles.map}
            javaScriptEnabled
            domStorageEnabled
            originWhitelist={['*']}
            onError={() => setError('Map failed to load')}
          />
        ) : null}

        {!fixMode && tracking && location && (
          <View style={styles.liveBadge}>
            <View style={styles.liveDot} />
            <Text style={styles.liveText}>Live • every 30s</Text>
          </View>
        )}

        {!fixMode && loading && location && (
          <View style={styles.refreshBadge}>
            <ActivityIndicator size="small" color="#fff" />
          </View>
        )}
      </View>

      {/* Bottom panel */}
      <View style={styles.bottomPanel}>

        {fixMode ? (
          /* ── Fix mode controls ── */
          <>
            {pendingPin ? (
              <View style={styles.pendingRow}>
                <Text style={styles.pendingText}>
                  📌  {pendingPin.lat.toFixed(5)},  {pendingPin.lon.toFixed(5)}
                </Text>
              </View>
            ) : (
              <View style={styles.pendingRow}>
                <Text style={styles.pendingHint}>Tap anywhere on the map above</Text>
              </View>
            )}

            <DarkBtn
              title={saving ? 'Saving…' : '💾  Save This Location'}
              onPress={savePin}
              disabled={!pendingPin || saving}
              style={styles.saveBtn}
            />
            <BackBtn
              onPress={() => { setFixMode(false); setPendingPin(null); }}
              label="← Cancel"
            />
          </>
        ) : (
          /* ── Normal view controls ── */
          <>
            <View style={styles.infoRow}>
              <View style={styles.infoLeft}>
                <View style={styles.infoLabelRow}>
                  <Text style={styles.infoSub}>Last Known Location</Text>
                  {isManual
                    ? <Text style={styles.badgeManual}>Pinned</Text>
                    : <Text style={styles.badgeIp}>IP Estimate</Text>}
                </View>
                <Text style={styles.infoMain} numberOfLines={1}>{locationLabel}</Text>
                {location && (
                  <Text style={styles.infoCoords}>
                    {location.lat.toFixed(5)},  {location.lon.toFixed(5)}
                  </Text>
                )}
              </View>
              <Text style={styles.infoEmoji}>📍</Text>
            </View>

            {!isManual && (
              <Text style={styles.ipWarning}>
                ⚠️  IP estimate may be inaccurate — tap Fix Location to pin the real spot
              </Text>
            )}

            <View style={styles.buttonRow}>
              <TouchableOpacity
                style={styles.fixBtn}
                onPress={() => setFixMode(true)}
                activeOpacity={0.8}>
                <Text style={styles.fixBtnText}>📌 Fix Location</Text>
              </TouchableOpacity>

              {isManual && (
                <TouchableOpacity
                  style={styles.resetBtn}
                  onPress={clearPin}
                  activeOpacity={0.8}>
                  <Text style={styles.resetBtnText}>Reset</Text>
                </TouchableOpacity>
              )}
            </View>

            <DarkBtn
              title={tracking ? '⏹  Stop Tracking' : '▶  Start Live Tracking'}
              onPress={() => {
                if (!tracking) { setLoading(true); fetchLocation(); }
                setTracking(t => !t);
              }}
              style={styles.trackBtn}
            />

            <BackBtn
              onPress={() => navigation.navigate('Dashboard')}
              label="← Back to Dashboard"
            />
          </>
        )}
      </View>
    </ScreenBg>
  );
}

const styles = StyleSheet.create({
  deniedContainer: {
    flex: 1, alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: 32, gap: 14,
  },
  deniedIcon: {fontSize: 52},
  deniedTitle: {fontSize: 20, fontWeight: '700', color: '#fff'},
  deniedSub: {fontSize: 14, color: 'rgba(255,255,255,0.5)', textAlign: 'center', lineHeight: 20},

  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    marginHorizontal: 18, marginTop: 6, marginBottom: 8,
  },
  headerTitle: {fontSize: 18, fontWeight: '700', color: '#fff'},
  headerSub: {fontSize: 12, color: 'rgba(255,255,255,0.45)', marginTop: 2},
  roleBadge: {borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5},
  guardianBadge: {backgroundColor: 'rgba(59,130,246,0.25)'},
  caregiverBadge: {backgroundColor: 'rgba(16,185,129,0.25)'},
  roleBadgeText: {fontSize: 11, fontWeight: '700', color: '#fff', textTransform: 'uppercase', letterSpacing: 0.5},

  mapContainer: {width: '100%', height: MAP_H, overflow: 'hidden', backgroundColor: '#0f172a'},
  map: {flex: 1, width: '100%', height: MAP_H, backgroundColor: '#0f172a'},
  mapPlaceholder: {flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12},
  placeholderText: {color: 'rgba(255,255,255,0.5)', fontSize: 14},
  errorText: {color: '#f87171', fontSize: 15, fontWeight: '600'},
  errorSub: {color: 'rgba(255,255,255,0.4)', fontSize: 12, textAlign: 'center', paddingHorizontal: 24},

  liveBadge: {
    position: 'absolute', top: 12, right: 12,
    backgroundColor: 'rgba(28,33,32,0.85)', borderRadius: 20,
    paddingHorizontal: 14, paddingVertical: 6,
    flexDirection: 'row', alignItems: 'center', gap: 8,
  },
  liveDot: {width: 8, height: 8, borderRadius: 4, backgroundColor: '#4ade80'},
  liveText: {fontSize: 12, fontWeight: '500', color: '#fff'},
  refreshBadge: {
    position: 'absolute', top: 12, left: 12,
    backgroundColor: 'rgba(28,33,32,0.75)', borderRadius: 20, padding: 8,
  },

  bottomPanel: {
    flex: 1, paddingHorizontal: 18, paddingTop: 14,
    paddingBottom: Platform.OS === 'ios' ? 36 : 20, gap: 10,
  },

  infoRow: {
    backgroundColor: 'rgba(255,255,255,0.07)', borderRadius: 18, padding: 14,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)',
  },
  infoLeft: {gap: 3, flex: 1},
  infoLabelRow: {flexDirection: 'row', alignItems: 'center', gap: 8},
  infoSub: {fontSize: 11, fontWeight: '300', color: 'rgba(255,255,255,0.5)'},
  badgeManual: {
    fontSize: 10, fontWeight: '700', color: '#10b981',
    backgroundColor: 'rgba(16,185,129,0.2)', paddingHorizontal: 7,
    paddingVertical: 2, borderRadius: 10,
  },
  badgeIp: {
    fontSize: 10, fontWeight: '700', color: '#f87171',
    backgroundColor: 'rgba(239,68,68,0.2)', paddingHorizontal: 7,
    paddingVertical: 2, borderRadius: 10,
  },
  infoMain: {fontSize: 15, fontWeight: '600', color: '#fff', maxWidth: width - 100},
  infoCoords: {
    fontSize: 11, color: 'rgba(255,255,255,0.35)',
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', marginTop: 2,
  },
  infoEmoji: {fontSize: 22},

  ipWarning: {fontSize: 11, color: '#fbbf24', textAlign: 'center'},

  buttonRow: {flexDirection: 'row', gap: 10},
  fixBtn: {
    flex: 1, backgroundColor: 'rgba(245,158,11,0.2)',
    borderRadius: 14, paddingVertical: 11,
    alignItems: 'center', borderWidth: 1, borderColor: 'rgba(245,158,11,0.4)',
  },
  fixBtnText: {fontSize: 14, fontWeight: '700', color: '#f59e0b'},
  resetBtn: {
    backgroundColor: 'rgba(239,68,68,0.15)', borderRadius: 14,
    paddingVertical: 11, paddingHorizontal: 18,
    alignItems: 'center', borderWidth: 1, borderColor: 'rgba(239,68,68,0.35)',
  },
  resetBtnText: {fontSize: 14, fontWeight: '700', color: '#f87171'},

  pendingRow: {
    backgroundColor: 'rgba(245,158,11,0.12)', borderRadius: 14, padding: 12,
    alignItems: 'center', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)',
  },
  pendingText: {fontSize: 13, fontWeight: '700', color: '#f59e0b'},
  pendingHint: {fontSize: 13, color: 'rgba(255,255,255,0.45)'},
  saveBtn: {marginTop: 0},
  trackBtn: {marginTop: 0},
});
