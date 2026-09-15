// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
package com.example.connecthealth;

import org.eclipse.jetty.server.Server;
import org.eclipse.jetty.servlet.ServletContextHandler;
import org.eclipse.jetty.servlet.ServletHolder;
import org.eclipse.jetty.websocket.server.config.JettyWebSocketServletContainerInitializer;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

/**
 * WebSocket server for ConnectHealth streaming transcription.
 * 
 * Accepts WebSocket connections from browsers, receives audio chunks,
 * forwards to ConnectHealth API, and streams transcripts back.
 */
public class StreamingServer {
    
    private static final int PORT = StreamingConfig.PORT;
    
    public static void main(String[] args) throws Exception {
        Server server = new Server(PORT);
        
        ServletContextHandler context = new ServletContextHandler(ServletContextHandler.SESSIONS);
        context.setContextPath("/");
        server.setHandler(context);
        
        // Add health check endpoint
        context.addServlet(new ServletHolder(new HttpServlet() {
            @Override
            protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
                resp.setStatus(HttpServletResponse.SC_OK);
                resp.setContentType("application/json");
                resp.getWriter().write("{\"status\":\"healthy\"}");
            }
        }), "/");
        
        context.addServlet(new ServletHolder(new HttpServlet() {
            @Override
            protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
                resp.setStatus(HttpServletResponse.SC_OK);
                resp.setContentType("application/json");
                resp.getWriter().write("{\"status\":\"healthy\"}");
            }
        }), "/health");
        
        // Configure WebSocket
        JettyWebSocketServletContainerInitializer.configure(context, (servletContext, wsContainer) -> {
            wsContainer.setMaxTextMessageSize(65535);
            wsContainer.setMaxBinaryMessageSize(1024 * 1024); // 1MB for audio chunks
            wsContainer.addMapping("/stream", WebSocketEndpoint.class);
        });
        
        System.out.println("╔══════════════════════════════════════════════════════════════╗");
        System.out.println("║       ConnectHealth Streaming WebSocket Server                ║");
        System.out.println("╠══════════════════════════════════════════════════════════════╣");
        System.out.println("║  WebSocket: ws://localhost:" + PORT + "/stream                       ║");
        System.out.println("║  Health:    http://localhost:" + PORT + "/                           ║");
        System.out.println("╠══════════════════════════════════════════════════════════════╣");
        System.out.println("║  Protocol:                                                   ║");
        System.out.println("║    → Send JSON: {\"type\":\"start\",\"sessionId\":\"...\"}          ║");
        System.out.println("║    → Send binary: raw PCM audio (16kHz, 16-bit, mono)        ║");
        System.out.println("║    → Send JSON: {\"type\":\"stop\"}                              ║");
        System.out.println("║    ← Receive: {\"type\":\"transcript\",\"text\":\"...\",\"final\":t/f}║");
        System.out.println("╚══════════════════════════════════════════════════════════════╝");
        
        server.start();
        server.join();
    }
}
