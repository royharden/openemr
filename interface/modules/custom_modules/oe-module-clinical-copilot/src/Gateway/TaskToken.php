<?php

/**
 * Patient-bound task token (HMAC-signed JWT-like, not a real JWT).
 *
 * The sidecar has no DB access, so the gateway hands it a 15-minute
 * scoped token that asserts: "This request is for patient_uuid X by user Y
 * with read-only scope, expiring at exp." The sidecar trusts the gateway
 * because the shared secret is known only to the two services.
 *
 * @package   OpenEMR
 * @author    Roy Harden <royhardenre@gmail.com>
 * @license   https://github.com/openemr/openemr/blob/master/LICENSE GNU General Public License 3
 */

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Gateway;

final class TaskToken
{
    public static function mint(
        string $sharedSecret,
        string $patientUuid,
        int $userId,
        ?string $encounterUuid,
        string $purposeOfUse,
        int $ttlSeconds = 900,
    ): string {
        $payload = [
            'patient_uuid' => $patientUuid,
            'user_id' => $userId,
            'encounter_uuid' => $encounterUuid,
            'scope' => 'read-only',
            'pou' => $purposeOfUse,
            'iat' => time(),
            'exp' => time() + $ttlSeconds,
        ];
        $body = base64_encode(json_encode($payload, JSON_UNESCAPED_SLASHES));
        $sig = hash_hmac('sha256', $body, $sharedSecret);
        return $body . '.' . $sig;
    }
}
