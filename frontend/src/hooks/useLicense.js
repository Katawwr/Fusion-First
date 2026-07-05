import { useState, useCallback } from 'react';
import { validateLicenseKey } from '../lib/api';

const LICENSE_STORAGE_KEY = 'fusionLicenseKey';

export default function useLicense() {
  const [licenseKey, setLicenseKey] = useState(() => {
    return localStorage.getItem(LICENSE_STORAGE_KEY) || '';
  });
  const [licenseValidating, setLicenseValidating] = useState(false);
  const [licenseError, setLicenseError] = useState('');

  const saveLicenseKey = useCallback((key) => {
    setLicenseKey(key);
    if (key) {
      localStorage.setItem(LICENSE_STORAGE_KEY, key);
    } else {
      localStorage.removeItem(LICENSE_STORAGE_KEY);
    }
  }, []);

  const validateLicense = useCallback(async (key, onSuccess) => {
    if (!key) return null;

    setLicenseValidating(true);
    setLicenseError('');

    try {
      const data = await validateLicenseKey(key);

      if (data.valid) {
        saveLicenseKey(key);
        setLicenseError('');
        if (onSuccess) {
          onSuccess(data);
        }
        return data;
      } else {
        setLicenseError(data.error || 'Invalid license key');
        saveLicenseKey('');
        return null;
      }
    } catch (error) {
      setLicenseError('Failed to validate license key');
      console.error('License validation error:', error);
      return null;
    } finally {
      setLicenseValidating(false);
    }
  }, [saveLicenseKey]);

  const clearLicense = useCallback(() => {
    saveLicenseKey('');
    setLicenseError('');
  }, [saveLicenseKey]);

  return {
    licenseKey,
    licenseValidating,
    licenseError,
    validateLicense,
    clearLicense,
    saveLicenseKey,
  };
}
