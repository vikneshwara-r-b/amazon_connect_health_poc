// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
/**
 * Connect Health EHR Interface Configuration
 * 
 * Update these values when deploying to different environments.
 * See DEPLOYMENT_GUIDE.md Step 3b for instructions.
 */

(function() {
    'use strict';
    
    // Detect environment based on hostname
    const hostname = window.location.hostname;
    
    // ==========================================================================
    // DEMO MODE
    // ==========================================================================
    window.DEMO_MODE = localStorage.getItem('demoMode') === 'true';
    
    window.demoHeaders = function(extra) {
        const h = extra ? Object.assign({}, extra) : {};
        if (window.DEMO_MODE) h['X-Demo-Mode'] = 'true';
        return h;
    };
    
    window.toggleDemoMode = function() {
        window.DEMO_MODE = !window.DEMO_MODE;
        localStorage.setItem('demoMode', window.DEMO_MODE);
        _updateDemoBadge();
        console.log('[Demo] Mode:', window.DEMO_MODE ? 'ON' : 'OFF');
    };
    
    function _updateDemoBadge() {
        let badge = document.getElementById('demoBadge');
        if (window.DEMO_MODE) {
            if (!badge) {
                badge = document.createElement('div');
                badge.id = 'demoBadge';
                badge.style.cssText = 'position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:99999;' +
                    'background:#f59e0b;color:#000;padding:3px 12px;border-radius:12px;font-size:11px;' +
                    'font-weight:600;letter-spacing:0.5px;cursor:pointer;user-select:none;opacity:0.9;' +
                    'font-family:-apple-system,BlinkMacSystemFont,sans-serif;box-shadow:0 1px 4px rgba(0,0,0,0.2);';
                badge.textContent = 'DEMO MODE';
                badge.title = 'Click or Ctrl+Shift+D to toggle off';
                badge.onclick = window.toggleDemoMode;
                document.body.appendChild(badge);
            }
            badge.style.display = 'block';
        } else if (badge) {
            badge.style.display = 'none';
        }
    }
    
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.shiftKey && e.key === 'D') {
            e.preventDefault();
            window.toggleDemoMode();
        }
    });
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', _updateDemoBadge);
    } else {
        _updateDemoBadge();
    }
    
    // ==========================================================================
    // COGNITO AUTHENTICATION
    // ==========================================================================
    // Set these after deploying the cognito-stack.yaml CloudFormation template.
    // Leave empty to disable authentication (local development default).
    window.COGNITO_CONFIG = {
        userPoolId: 'YOUR_COGNITO_USER_POOL_ID',
        clientId: 'YOUR_COGNITO_CLIENT_ID',
        region: 'us-east-1'
    };

    // ==========================================================================
    // CLINIC CONTACT NUMBERS
    // ==========================================================================
    // Replace these with your actual clinic phone numbers.
    // SCHEDULING_PHONE appears in the SMS follow-up message template.
    // OFFICE_PHONE appears in the UI footer and SMS message.
    window.CLINIC_PHONE = {
        schedulingNumber: '(555) 123-4567',   // toll-free or scheduling line
        officeNumber: '(555) 123-4567'        // front desk / office line
    };

    // ==========================================================================
    // CLINIC TIMEZONE
    // ==========================================================================
    // IANA timezone name the clinic operates in. Drives the schedule screen's
    // appointment-slot times and "today" date header — without this, those would
    // silently follow whatever timezone the viewer's own browser/OS happens to be
    // set to, which is wrong for a clinic scheduling display (a patient viewing
    // from another timezone would see appointment times shifted to their own clock).
    // Change this to your clinic's actual timezone.
    window.APP_TIMEZONE = 'America/Lima';

    // Returns the current date/time as plain numeric parts (year, month 1-12, day,
    // hour 0-23, minute, second), evaluated in `timeZone` (defaults to APP_TIMEZONE)
    // rather than the browser's local timezone. Use this instead of `new Date()` +
    // getHours()/getDate() etc. wherever a wall-clock value needs to reflect the
    // clinic's timezone, not the viewer's.
    window.getZonedNow = function(timeZone) {
        const tz = timeZone || window.APP_TIMEZONE || Intl.DateTimeFormat().resolvedOptions().timeZone;
        const parts = new Intl.DateTimeFormat('en-US', {
            timeZone: tz,
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit',
            hour12: false
        }).formatToParts(new Date());
        const get = (type) => parseInt(parts.find(p => p.type === type).value, 10);
        let hour = get('hour');
        if (hour === 24) hour = 0; // some locales render midnight as "24" with hour12:false
        return {
            year: get('year'),
            month: get('month'), // 1-12
            day: get('day'),
            hour: hour,
            minute: get('minute'),
            second: get('second')
        };
    };

    // Environment configurations
    // Update the 'deployed' block with your CloudFront distribution URLs after deployment.
    const configs = {
        local: {
            WS_URL: 'ws://localhost:8081/stream',
            BACKEND_URL: 'http://localhost:5000',
            ENV_NAME: 'local'
        },
        deployed: {
            WS_URL: 'wss://<YOUR_WSS_CLOUDFRONT>.cloudfront.net/stream',
            BACKEND_URL: 'https://<YOUR_BACKEND_CLOUDFRONT>.cloudfront.net',
            ENV_NAME: 'deployed'
        }
    };
    
    let activeConfig;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        activeConfig = configs.local;
    } else {
        activeConfig = configs.deployed;
    }
    
    window.WS_URL = activeConfig.WS_URL;
    window.BACKEND_URL = activeConfig.BACKEND_URL;
    window.ENV_NAME = activeConfig.ENV_NAME;
    
    console.log('[Config] Environment:', activeConfig.ENV_NAME);
    console.log('[Config] WebSocket URL:', activeConfig.WS_URL);
    console.log('[Config] Backend URL:', activeConfig.BACKEND_URL);
})();
