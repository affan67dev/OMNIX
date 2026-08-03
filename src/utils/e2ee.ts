import { apiJson, getCurrentUserId } from './socialApi';
import { getSecureJson, setSecureJson } from './cryptoStorage';

type JsonWebKeyPair = {
  publicKey: JsonWebKey;
  privateKey: JsonWebKey;
};

export type PublicKeyBundle = {
  user_id: string;
  algorithm: 'P-256/AES-256-GCM';
  identity_public_key: string;
  prekey_public_key: string;
  prekey_key_id: string;
  device_id: string;
  updated_at?: string;
};

export type EncryptedMessageEnvelope = {
  encrypted_payload: string;
  encryption_nonce: string;
  sender_ephemeral_public_key: string;
  recipient_key_id: string;
  encryption_algorithm: 'ECDH-P256/AES-256-GCM';
};

type LocalKeyBundle = {
  identityKeyPair: JsonWebKeyPair;
  prekeyPair: JsonWebKeyPair;
  prekeyKeyId: string;
};

function getKeyBundleStorageKey() {
  return `e2ee:keybundle:${getCurrentUserId() || 'anonymous'}`;
}

function bytesToBase64(input: Uint8Array): string {
  return window.btoa(String.fromCharCode(...input));
}

function base64ToBytes(input: string): Uint8Array<ArrayBuffer> {
  const raw = Uint8Array.from(window.atob(input), (char) => char.charCodeAt(0));
  return new Uint8Array(raw) as Uint8Array<ArrayBuffer>;
}

async function exportPublicKeyBase64(key: CryptoKey): Promise<string> {
  const raw = await crypto.subtle.exportKey('raw', key);
  return bytesToBase64(new Uint8Array(raw));
}

async function importPublicKeyBase64(rawKey: string): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    base64ToBytes(rawKey),
    { name: 'ECDH', namedCurve: 'P-256' },
    true,
    [],
  );
}

async function generateEcdhKeyPair(): Promise<CryptoKeyPair> {
  return crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']) as Promise<CryptoKeyPair>;
}

async function exportKeyPair(keyPair: CryptoKeyPair): Promise<JsonWebKeyPair> {
  const publicKey = await crypto.subtle.exportKey('jwk', keyPair.publicKey);
  const privateKey = await crypto.subtle.exportKey('jwk', keyPair.privateKey);
  return { publicKey, privateKey };
}

async function importStoredKeyPair(pair: JsonWebKeyPair): Promise<CryptoKeyPair> {
  const publicKey = await crypto.subtle.importKey('jwk', pair.publicKey, { name: 'ECDH', namedCurve: 'P-256' }, true, []);
  const privateKey = await crypto.subtle.importKey('jwk', pair.privateKey, { name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  return { publicKey, privateKey };
}

async function deriveAesKey(sharedBits: ArrayBuffer, salt: Uint8Array<ArrayBuffer>, info: string): Promise<CryptoKey> {
  const hkdfInput = await crypto.subtle.importKey('raw', sharedBits, 'HKDF', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'HKDF', hash: 'SHA-256', salt, info: new TextEncoder().encode(info) },
    hkdfInput,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

export async function ensureLocalPublicKeyBundle(): Promise<PublicKeyBundle> {
  let stored = await getSecureJson<LocalKeyBundle>(getKeyBundleStorageKey());
  if (!stored) {
    const identityKeyPair = await exportKeyPair(await generateEcdhKeyPair());
    const prekeyPair = await exportKeyPair(await generateEcdhKeyPair());
    stored = {
      identityKeyPair,
      prekeyPair,
      prekeyKeyId: `prekey-${Date.now()}`,
    };
    await setSecureJson(getKeyBundleStorageKey(), stored);
  }
  const identity = await importStoredKeyPair(stored.identityKeyPair);
  const prekey = await importStoredKeyPair(stored.prekeyPair);
  return {
    user_id: getCurrentUserId(),
    algorithm: 'P-256/AES-256-GCM',
    identity_public_key: await exportPublicKeyBase64(identity.publicKey),
    prekey_public_key: await exportPublicKeyBase64(prekey.publicKey),
    prekey_key_id: stored.prekeyKeyId,
    device_id: 'primary-device',
  };
}

async function localPrekeyPair(): Promise<{ keyId: string; keyPair: CryptoKeyPair }> {
  const stored = await getSecureJson<LocalKeyBundle>(getKeyBundleStorageKey());
  if (!stored) {
    await ensureLocalPublicKeyBundle();
  }
  const resolved = await getSecureJson<LocalKeyBundle>(getKeyBundleStorageKey());
  if (!resolved) {
    throw new Error('Unable to load local E2EE keys');
  }
  return { keyId: resolved.prekeyKeyId, keyPair: await importStoredKeyPair(resolved.prekeyPair) };
}

export async function syncLocalPublicKeyBundle(): Promise<PublicKeyBundle> {
  const bundle = await ensureLocalPublicKeyBundle();
  const response = await apiJson<{ success: boolean; bundle: PublicKeyBundle }>('/api/v1/security/e2ee/key-bundle', {
    method: 'PUT',
    body: JSON.stringify(bundle),
  });
  return response.bundle;
}

export async function fetchRemotePublicKeyBundle(userId: string): Promise<PublicKeyBundle> {
  const response = await apiJson<{ success: boolean; bundle: PublicKeyBundle }>(`/api/v1/security/e2ee/key-bundle/${userId}`);
  return response.bundle;
}

export async function encryptDirectMessage(input: {
  conversationId: string;
  recipientUserId: string;
  recipientBundle: PublicKeyBundle;
  plaintext: string;
}): Promise<EncryptedMessageEnvelope> {
  const ephemeralKeyPair = await generateEcdhKeyPair();
  const remotePrekey = await importPublicKeyBase64(input.recipientBundle.prekey_public_key);
  const sharedBits = await crypto.subtle.deriveBits({ name: 'ECDH', public: remotePrekey }, ephemeralKeyPair.privateKey, 256);
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const salt = new TextEncoder().encode(`${input.conversationId}:${input.recipientUserId}:${input.recipientBundle.prekey_key_id}`);
  const aesKey = await deriveAesKey(sharedBits, salt, 'bytechat/e2ee/v1');
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce }, aesKey, new TextEncoder().encode(input.plaintext));
  return {
    encrypted_payload: bytesToBase64(new Uint8Array(encrypted)),
    encryption_nonce: bytesToBase64(nonce),
    sender_ephemeral_public_key: await exportPublicKeyBase64(ephemeralKeyPair.publicKey),
    recipient_key_id: input.recipientBundle.prekey_key_id,
    encryption_algorithm: 'ECDH-P256/AES-256-GCM',
  };
}

export async function decryptDirectMessage(input: {
  conversationId: string;
  senderUserId: string;
  encrypted_payload: string;
  encryption_nonce: string;
  sender_ephemeral_public_key: string;
  recipient_key_id: string;
}): Promise<string> {
  const { keyId, keyPair } = await localPrekeyPair();
  if (keyId !== input.recipient_key_id) {
    throw new Error('Local device does not have the required prekey');
  }
  const remoteEphemeral = await importPublicKeyBase64(input.sender_ephemeral_public_key);
  const sharedBits = await crypto.subtle.deriveBits({ name: 'ECDH', public: remoteEphemeral }, keyPair.privateKey, 256);
  const salt = new TextEncoder().encode(`${input.conversationId}:${getCurrentUserId()}:${input.recipient_key_id}`);
  const aesKey = await deriveAesKey(sharedBits, salt, 'bytechat/e2ee/v1');
  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: base64ToBytes(input.encryption_nonce) },
    aesKey,
    base64ToBytes(input.encrypted_payload),
  );
  return new TextDecoder().decode(decrypted);
}