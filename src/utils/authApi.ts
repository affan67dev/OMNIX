import { supabase } from '../supabase/supabaseClient';

export type AuthUser = { id: string; email?: string; username?: string; phone?: string };
export type AuthSuccessResponse = { success: boolean; access_token: string; refresh_token: string; expires_in: number; user: AuthUser };

function normalizePhone(countryCode: string, phone: string): string {
  const cc = countryCode.trim().replace(/[^\d+]/g, ''); const digits = phone.replace(/\D/g, '');
  if (!/^\+\d{1,4}$/.test(cc)) throw new Error('Enter a valid country code.');
  if (digits.length < 8 || digits.length > 15) throw new Error('Enter a valid phone number.');
  return `${cc}${digits}`;
}
function validateUsername(value: string): string { const username = value.trim().toLowerCase(); if (!/^[a-z0-9_]{3,30}$/.test(username)) throw new Error('Username must be 3–30 characters using letters, numbers or underscores.'); return username; }
function validatePassword(password: string): void { if (password.length < 8) throw new Error('Password must be at least 8 characters.'); if (password.length > 72) throw new Error('Password is too long.'); }
function toAuthError(error: { message?: string; status?: number } | null): Error { const message = error?.message || 'Authentication request failed.'; const lower = message.toLowerCase(); if (lower.includes('rate') || error?.status === 429) return new Error('Too many attempts. Please wait and try again.'); if (lower.includes('invalid') && lower.includes('otp')) return new Error('The OTP is incorrect or expired.'); if (lower.includes('expired')) return new Error('The OTP has expired. Request a new code.'); if (lower.includes('already') || lower.includes('duplicate') || lower.includes('unique')) return new Error('That account information is already in use.'); if (lower.includes('weak password')) return new Error('Choose a stronger password.'); return new Error(message); }

export function persistAuthSession(session: { access_token: string; refresh_token: string; expires_in: number; user: AuthUser }): void { window.localStorage.setItem('access_token', session.access_token); window.localStorage.setItem('refresh_token', session.refresh_token); window.localStorage.setItem('user', JSON.stringify(session.user)); }
export async function getCurrentSession() { const { data, error } = await supabase.auth.getSession(); if (error) throw toAuthError(error); return data.session; }

export async function loginWithPassword(identity: string, password: string): Promise<AuthSuccessResponse> {
  const value = identity.trim(); if (!value || !password) throw new Error('Email/phone and password are required.');
  const credentials = value.includes('@') ? { email: value.toLowerCase(), password } : { phone: value, password };
  const { data, error } = await supabase.auth.signInWithPassword(credentials); if (error || !data.session || !data.user) throw toAuthError(error);
  const username = String(data.user.user_metadata?.username || data.user.email?.split('@')[0] || data.user.phone || 'user');
  const response = { success: true, access_token: data.session.access_token, refresh_token: data.session.refresh_token, expires_in: data.session.expires_in || 3600, user: { id: data.user.id, email: data.user.email, username, phone: data.user.phone } }; persistAuthSession(response); return response;
}

export async function sendSignupOtp(countryCode: string, phoneNumber: string): Promise<{ phone: string; expiresIn: number; challenge_id: string; otp_code?: string }> {
  const phone = normalizePhone(countryCode, phoneNumber); const { error } = await supabase.auth.signInWithOtp({ phone, options: { shouldCreateUser: true } }); if (error) throw toAuthError(error);
  return { phone, expiresIn: 60, challenge_id: phone };
}

export async function verifySignupOtp(phone: string, otpCode: string): Promise<AuthSuccessResponse> {
  if (!/^\d{6}$/.test(otpCode)) throw new Error('Enter the 6-digit OTP.');
  const { data, error } = await supabase.auth.verifyOtp({ phone, token: otpCode, type: 'sms' }); if (error || !data.session || !data.user) throw toAuthError(error);
  const username = String(data.user.user_metadata?.username || data.user.phone || 'user');
  return { success: true, access_token: data.session.access_token, refresh_token: data.session.refresh_token, expires_in: data.session.expires_in || 3600, user: { id: data.user.id, email: data.user.email, username, phone: data.user.phone } };
}

export async function checkSignupAvailability(email: string, username: string): Promise<{ email_available: boolean; username_available: boolean }> {
  const normalizedUsername = validateUsername(username); const normalizedEmail = email.trim().toLowerCase(); if (!/^\S+@\S+\.\S+$/.test(normalizedEmail)) throw new Error('Enter a valid email address.');
  const { data, error } = await supabase.from('profiles').select('user_id,username').eq('username', normalizedUsername).maybeSingle(); if (error) throw new Error('Unable to validate username right now.');
  return { username_available: !data, email_available: true };
}

export async function completeSignup(params: { username: string; email: string; password: string; phone: string; legalAccepted: boolean }): Promise<AuthSuccessResponse> {
  if (!params.legalAccepted) throw new Error('You must accept the Terms & Conditions and Privacy Policy.');
  const username = validateUsername(params.username); const email = params.email.trim().toLowerCase(); if (!/^\S+@\S+\.\S+$/.test(email)) throw new Error('Enter a valid email address.'); validatePassword(params.password);
  const availability = await checkSignupAvailability(email, username); if (!availability.username_available) throw new Error('Username is already taken.');
  const { data: userData, error: userError } = await supabase.auth.updateUser({ email, password: params.password, data: { username, mobile: params.phone, terms_accepted: true, privacy_accepted: true, legal_accepted_at: new Date().toISOString() } });
  if (userError || !userData.user) throw toAuthError(userError);
  const { error: profileError } = await supabase.from('profiles').update({ username, full_name: username, mobile: params.phone }).eq('user_id', userData.user.id);
  if (profileError) { if (String(profileError.code || '').includes('23505')) throw new Error('Username is already taken.'); throw new Error('Account profile could not be completed. Please try again.'); }
  const session = await getCurrentSession(); if (!session) throw new Error('Account was created but the session could not be established. Please log in.');
  const response = { success: true, access_token: session.access_token, refresh_token: session.refresh_token, expires_in: session.expires_in || 3600, user: { id: userData.user.id, email: userData.user.email, username, phone: userData.user.phone || params.phone } }; persistAuthSession(response); return response;
}

export async function signupWithWizard(params: any): Promise<AuthSuccessResponse> { return completeSignup({ username: params.username, email: params.email, password: params.password, phone: `${params.phone_country_code || '+1'}${String(params.phone_number || '').replace(/\D/g, '')}`, legalAccepted: Boolean(params.legal_accepted) }); }
export async function signInWithGoogle(): Promise<void> { const { error } = await supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: `${window.location.origin}/` } }); if (error) throw toAuthError(error); }
export async function signOut(): Promise<void> { const { error } = await supabase.auth.signOut(); window.localStorage.removeItem('user'); window.localStorage.removeItem('access_token'); window.localStorage.removeItem('refresh_token'); if (error) throw toAuthError(error); }
export async function requestPasswordReset(email: string): Promise<void> { const value = email.trim().toLowerCase(); if (!/^\S+@\S+\.\S+$/.test(value)) throw new Error('Enter a valid email address.'); const { error } = await supabase.auth.resetPasswordForEmail(value, { redirectTo: `${window.location.origin}/forgot-password` }); if (error) throw toAuthError(error); }
export async function updatePassword(password: string): Promise<void> { validatePassword(password); const { error } = await supabase.auth.updateUser({ password }); if (error) throw toAuthError(error); }
