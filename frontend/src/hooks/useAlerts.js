import {useEffect, useState} from 'react';
import {getUnreadAlerts, markAlertAsRead, clearAllAlerts} from '../services/alertService';

export function useAlerts(patientId, pollIntervalMs = 5000) {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchAlerts = async () => {
    if (!patientId) return;

    setLoading(true);
    setError(null);

    try {
      const data = await getUnreadAlerts(patientId);
      setAlerts(data.alerts || []);
    } catch (err) {
      console.log('[ALERTS] Error fetching alerts:', err.message);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const dismissAlert = async (alertId) => {
    try {
      await markAlertAsRead(alertId);
      setAlerts(prev => prev.filter(a => a._id !== alertId));
    } catch (err) {
      console.log('[ALERTS] Error dismissing alert:', err.message);
    }
  };

  const dismissAllAlerts = async () => {
    if (!patientId) return;

    try {
      await clearAllAlerts(patientId);
      await fetchAlerts();
    } catch (err) {
      console.log('[ALERTS] Error clearing all alerts:', err.message);
      setError(err.message);
    }
  };

  // Poll for new alerts periodically
  useEffect(() => {
    fetchAlerts();

    const interval = setInterval(fetchAlerts, pollIntervalMs);

    return () => clearInterval(interval);
  }, [patientId, pollIntervalMs]);

  return {
    alerts,
    loading,
    error,
    dismissAlert,
    dismissAllAlerts,
    refetch: fetchAlerts,
  };
}
