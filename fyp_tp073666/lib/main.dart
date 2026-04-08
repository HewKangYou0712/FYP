import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:provider/provider.dart';
import 'firebase_options.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'package:intl/intl.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform);
  runApp(
    ChangeNotifierProvider(
      create: (_) => ThemeProvider(),
      child: const SmartDryingRackApp(),
    ),
  );
}

class ThemeProvider extends ChangeNotifier {
  ThemeMode themeMode = ThemeMode.system;

  bool get isDarkMode {
    if (themeMode == ThemeMode.system) {
      return WidgetsBinding.instance.platformDispatcher.platformBrightness ==
          Brightness.dark;
    }
    return themeMode == ThemeMode.dark;
  }

  void toggleTheme(bool isOn) {
    themeMode = isOn ? ThemeMode.dark : ThemeMode.light;
    notifyListeners();
  }
}

class SmartDryingRackApp extends StatelessWidget {
  const SmartDryingRackApp({super.key});
  @override
  Widget build(BuildContext context) {
    final themeProvider = Provider.of<ThemeProvider>(context);
    return MaterialApp(
      title: 'Smart Rack',
      themeMode: themeProvider.themeMode,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      home: const AuthGate(),
    );
  }
}

class AuthGate extends StatelessWidget {
  const AuthGate({super.key});
  @override
  Widget build(BuildContext context) {
    return StreamBuilder<User?>(
      stream: FirebaseAuth.instance.authStateChanges(),
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const LoginRegisterScreen();
        }
        return const MainAppScreen();
      },
    );
  }
}

class MainAppScreen extends StatefulWidget {
  const MainAppScreen({super.key});
  @override
  State<MainAppScreen> createState() => _MainAppScreenState();
}

class _MainAppScreenState extends State<MainAppScreen> {
  int _selectedIndex = 0;

  // Define pages as a list of widgets
  static final List<Widget> _pages = <Widget>[
    const HomePage(),
    const CameraPage(),
    const StatusPage(),
    const ProfilePage(),
  ];

  void _onItemTapped(int index) => setState(() => _selectedIndex = index);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      // Use IndexedStack to keep all pages alive in background
      body: IndexedStack(index: _selectedIndex, children: _pages),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: _onItemTapped,
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(icon: Icon(Icons.videocam), label: 'Camera'),
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Status'),
          NavigationDestination(icon: Icon(Icons.person), label: 'Profile'),
        ],
      ),
    );
  }
}

// Status Page (Real Log)
class StatusPage extends StatelessWidget {
  const StatusPage({super.key});
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Activity Log')),
      body: StreamBuilder<QuerySnapshot>(
        stream: FirebaseFirestore.instance
            .collection('system_events')
            .orderBy('timestamp', descending: true)
            .limit(20)
            .snapshots(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final docs = snapshot.data!.docs;
          if (docs.isEmpty) {
            return const Center(child: Text("No recent activity"));
          }

          return ListView.builder(
            itemCount: docs.length,
            itemBuilder: (ctx, i) {
              final data = docs[i].data() as Map<String, dynamic>;
              final msg = data['message'] ?? 'Unknown';
              final ts =
                  (data['timestamp'] as Timestamp?)?.toDate() ?? DateTime.now();
              return Card(
                margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                child: ListTile(
                  leading: const Icon(Icons.info, color: Colors.blue),
                  title: Text(msg),
                  subtitle: Text(DateFormat('MMM d, h:mm:ss a').format(ts)),
                ),
              );
            },
          );
        },
      ),
    );
  }
}

// Home Page
class HomePage extends StatelessWidget {
  const HomePage({super.key});
  Future<void> _sendCmd(String c) async {
    try {
      await FirebaseFirestore.instance
          .collection('control')
          .doc('motor_command')
          .set({'command': c, 'timestamp': FieldValue.serverTimestamp()});
    } catch (e) {
      print("Error: $e");
    }
  }

  // Time Schedule Logic
  Future<void> _pickTimeAndSchedule(BuildContext context) async {
    final targetDoc = await FirebaseFirestore.instance
        .collection('config')
        .doc('target_position')
        .get();

    // Check Cloud status but allow local override if needed later (simplified for now)
    if (!targetDoc.exists) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text("⚠️ Limits not set! Calibrate first in Camera Page."),
            backgroundColor: Colors.red,
          ),
        );
      }
      return;
    }

    final TimeOfDay? picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.now(),
    );

    if (picked != null && context.mounted) {
      final String? action = await showDialog<String>(
        context: context,
        builder: (BuildContext ctx) {
          return SimpleDialog(
            title: const Text('Select Action'),
            children: <Widget>[
              SimpleDialogOption(
                onPressed: () => Navigator.pop(ctx, 'auto_extend'),
                child: const ListTile(
                  leading: Icon(
                    Icons.keyboard_double_arrow_up,
                    color: Colors.green,
                  ),
                  title: Text('Extend'),
                ),
              ),
              SimpleDialogOption(
                onPressed: () => Navigator.pop(ctx, 'auto_retract'),
                child: const ListTile(
                  leading: Icon(
                    Icons.keyboard_double_arrow_down,
                    color: Colors.blue,
                  ),
                  title: Text('Retract'),
                ),
              ),
            ],
          );
        },
      );

      if (action != null && context.mounted) {
        final String timeStr =
            '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';

        await FirebaseFirestore.instance
            .collection('config')
            .doc('schedule')
            .set({
              'time': timeStr,
              'action': action,
              'enabled': true,
              'last_updated': FieldValue.serverTimestamp(),
            });

        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                "Scheduled ${action == 'auto_extend' ? 'Extend' : 'Retract'} at $timeStr",
              ),
              backgroundColor: Colors.green,
            ),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final stream = FirebaseFirestore.instance
        .collection('sensor_data')
        .doc('live_data')
        .snapshots();

    final scheduleStream = FirebaseFirestore.instance
        .collection('config')
        .doc('schedule')
        .snapshots();

    return Scaffold(
      appBar: AppBar(title: const Text('Dashboard')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: StreamBuilder<DocumentSnapshot>(
          stream: stream,
          builder: (context, snapshot) {
            if (!snapshot.hasData) {
              return const Center(child: CircularProgressIndicator());
            }
            var data = snapshot.data!.data() as Map<String, dynamic>? ?? {};
            double temp = (data['temp'] ?? 0.0).toDouble();
            double hum = (data['hum'] ?? 0.0).toDouble();
            double lux = (data['lux'] ?? 0.0).toDouble();
            bool rain = data['rain'] ?? false;
            bool bird = data['bird_repellent'] ?? false;
            String status = data['motor_status'] ?? 'stopped';
            double frontDist = (data['front_dist'] ?? 0.0).toDouble();
            double backDist = (data['back_dist'] ?? 0.0).toDouble();

            String frontText = frontDist < 200
                ? '${frontDist.toStringAsFixed(0)} cm'
                : 'Clear';
            String backText = backDist < 200
                ? '${backDist.toStringAsFixed(0)} cm'
                : 'Clear';

            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildWeatherCard(temp, hum, lux, rain),
                const SizedBox(height: 12),
                _buildStatusCard(status, rain),
                const SizedBox(height: 12),

                // Schedule Card
                StreamBuilder<DocumentSnapshot>(
                  stream: scheduleStream,
                  builder: (ctx, schedSnap) {
                    String schedText = "No Schedule Set";
                    if (schedSnap.hasData && schedSnap.data!.exists) {
                      var sData =
                          schedSnap.data!.data() as Map<String, dynamic>? ?? {};
                      if (sData['enabled'] == true) {
                        String action = sData['action'] == 'auto_extend'
                            ? 'Extend'
                            : 'Retract';
                        schedText = "$action at ${sData['time']}";
                      } else {
                        schedText = "Schedule Disabled";
                      }
                    }

                    return Card(
                      color: Colors.purple.withValues(alpha: 0.1),
                      child: ListTile(
                        leading: const Icon(
                          Icons.alarm,
                          color: Colors.purple,
                          size: 32,
                        ),
                        title: const Text(
                          "Daily Schedule",
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        subtitle: Text(schedText),
                        trailing: ElevatedButton(
                          onPressed: () => _pickTimeAndSchedule(context),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: Colors.purple,
                            foregroundColor: Colors.white,
                          ),
                          child: const Text("Set"),
                        ),
                      ),
                    );
                  },
                ),

                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _buildDataCard(
                        Icons.thermostat,
                        'Temp',
                        '${temp.toStringAsFixed(1)}°C',
                        Colors.orange,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildDataCard(
                        Icons.water,
                        'Humidity',
                        '${hum.toStringAsFixed(0)}%',
                        Colors.blue,
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _buildDataCard(
                        Icons.wb_sunny,
                        'Light',
                        '${lux.toStringAsFixed(0)} Lx',
                        Colors.amber,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildDataCard(
                        Icons.surround_sound,
                        'Repellent',
                        bird ? "ON" : "OFF",
                        bird ? Colors.red : Colors.grey,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: _buildDataCard(
                        Icons.arrow_upward,
                        'Front',
                        frontText,
                        Colors.teal,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: _buildDataCard(
                        Icons.arrow_downward,
                        'Back',
                        backText,
                        Colors.purple,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 20),
                const Text(
                  'Manual Control',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () => _sendCmd('bird_on'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: bird ? Colors.red : null,
                          foregroundColor: bird ? Colors.white : null,
                        ),
                        child: const Text("Bird ON"),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () => _sendCmd('bird_off'),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: !bird ? Colors.grey : null,
                          foregroundColor: !bird ? Colors.white : null,
                        ),
                        child: const Text("Bird OFF"),
                      ),
                    ),
                  ],
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  // Weather "Nowcasting" Card
  Widget _buildWeatherCard(double temp, double hum, double lux, bool rain) {
    String title = "Unknown";
    String subtitle = "Waiting for sensors...";
    IconData icon = Icons.question_mark;
    Color color = Colors.grey;

    if (rain) {
      title = "RAINING!";
      subtitle = "Drying Rack Retracting";
      icon = Icons.thunderstorm;
      color = Colors.red;
    } else if (lux > 1000 && hum < 60) {
      title = "Excellent Drying";
      subtitle = "Sunny & Dry";
      icon = Icons.wb_sunny;
      color = Colors.orange;
    } else if (lux > 200 && hum < 75) {
      title = "Good Conditions";
      subtitle = "Cloudy but Dry";
      icon = Icons.cloud;
      color = Colors.blue;
    } else if (hum > 85) {
      title = "Rain Likely";
      subtitle = "High Humidity Detected";
      icon = Icons.water_drop;
      color = Colors.indigo;
    } else {
      title = "Poor Conditions";
      subtitle = "Low Light or Night";
      icon = Icons.nights_stay;
      color = Colors.blueGrey;
    }

    return Card(
      color: color.withValues(alpha: 0.1),
      child: ListTile(
        leading: Icon(icon, color: color, size: 40),
        title: Text(
          title,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            color: color,
            fontSize: 18,
          ),
        ),
        subtitle: Text(subtitle),
      ),
    );
  }

  Widget _buildStatusCard(String status, bool rain) {
    return Card(
      color: rain ? Colors.blueGrey : Colors.green,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(
              rain ? Icons.cloudy_snowing : Icons.check_circle,
              size: 48,
              color: Colors.white,
            ),
            Text(
              status.toUpperCase(),
              style: const TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: Colors.white,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDataCard(
    IconData icon,
    String label,
    String value,
    Color color,
  ) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Icon(icon, color: color, size: 28),
            Text(
              value,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            Text(label, style: const TextStyle(color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}

// Camera Page
class CameraPage extends StatefulWidget {
  const CameraPage({super.key});
  @override
  State<CameraPage> createState() => _CameraPageState();
}

class _CameraPageState extends State<CameraPage> {
  final _piConfigStream = FirebaseFirestore.instance
      .collection('config')
      .doc('pi_config')
      .snapshots();

  final _targetStream = FirebaseFirestore.instance
      .collection('config')
      .doc('target_position')
      .snapshots();

  WebViewController? _controller;
  String? _streamUrl;
  bool _isLoading = true;

  // Local state to track if we just set the limits
  bool _localLimitsSet = false;

  void _cmd(String c) {
    FirebaseFirestore.instance.collection('control').doc('motor_command').set({
      'command': c,
      'timestamp': FieldValue.serverTimestamp(),
    });
  }

  Future<void> _confirmAndCmd(String cmd, String title, String content) async {
    final bool? confirm = await showDialog<bool>(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text(title),
          content: Text(content),
          actions: <Widget>[
            TextButton(
              child: const Text("Cancel"),
              onPressed: () => Navigator.of(context).pop(false),
            ),
            TextButton(
              child: const Text("Confirm"),
              onPressed: () => Navigator.of(context).pop(true),
            ),
          ],
        );
      },
    );

    if (confirm == true) {
      _cmd(cmd);

      if (cmd == 'set_extend_position') {
        setState(() {
          _localLimitsSet = true;
        });
      }

      await FirebaseFirestore.instance.collection('system_events').add({
        'message': 'User Action: $title',
        'timestamp': FieldValue.serverTimestamp(),
      });

      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text("$title Command Sent!")));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Live Camera Feed')),
      body: Column(
        children: [
          SizedBox(
            height: 260,
            width: double.infinity,
            child: StreamBuilder<DocumentSnapshot>(
              stream: _piConfigStream,
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting &&
                    _streamUrl == null) {
                  return const Center(child: CircularProgressIndicator());
                }
                if (!snapshot.hasData || !snapshot.data!.exists) {
                  return const Center(child: Text('Waiting for Pi...'));
                }

                var data = snapshot.data!.data() as Map<String, dynamic>? ?? {};
                String? piIpAddress = data['ip_address'];

                if (piIpAddress == null) {
                  return const Center(child: Text('Pi IP not found.'));
                }

                final newStreamUrl = 'http://$piIpAddress:8000/video_feed';

                if (newStreamUrl != _streamUrl) {
                  WidgetsBinding.instance.addPostFrameCallback((_) {
                    if (mounted) {
                      setState(() {
                        _streamUrl = newStreamUrl;
                        _isLoading = true;
                        _controller = WebViewController()
                          ..setJavaScriptMode(JavaScriptMode.unrestricted)
                          ..setBackgroundColor(const Color(0x00000000))
                          ..loadRequest(Uri.parse(_streamUrl!));
                      });
                    }
                  });
                }

                return Container(
                  color: Colors.black,
                  child: Stack(
                    alignment: Alignment.center,
                    children: [
                      if (_controller != null)
                        WebViewWidget(controller: _controller!),
                      if (_isLoading || _controller == null)
                        const CircularProgressIndicator(),
                    ],
                  ),
                );
              },
            ),
          ),

          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  const Text(
                    "One-Click Actions",
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 10),

                  StreamBuilder<DocumentSnapshot>(
                    stream: _targetStream,
                    builder: (context, snapshot) {
                      bool cloudLimitsSet =
                          snapshot.hasData && snapshot.data!.exists;
                      bool limitsSet = cloudLimitsSet || _localLimitsSet;

                      return Column(
                        children: [
                          Row(
                            children: [
                              Expanded(
                                child: ElevatedButton.icon(
                                  onPressed: limitsSet
                                      ? () => _cmd('auto_extend')
                                      : null,
                                  icon: const Icon(
                                    Icons.keyboard_double_arrow_up,
                                  ),
                                  label: const Text("Auto Extend"),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.blue,
                                    foregroundColor: Colors.white,
                                    padding: const EdgeInsets.symmetric(
                                      vertical: 12,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: ElevatedButton.icon(
                                  onPressed: limitsSet
                                      ? () => _cmd('auto_retract')
                                      : null,
                                  icon: const Icon(
                                    Icons.keyboard_double_arrow_down,
                                  ),
                                  label: const Text("Auto Retract"),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.blue,
                                    foregroundColor: Colors.white,
                                    padding: const EdgeInsets.symmetric(
                                      vertical: 12,
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                          if (!limitsSet)
                            const Padding(
                              padding: EdgeInsets.only(top: 8.0),
                              child: Text(
                                "⚠️ Set Limits in Profile to enable Auto",
                                style: TextStyle(
                                  color: Colors.red,
                                  fontSize: 12,
                                ),
                              ),
                            ),
                        ],
                      );
                    },
                  ),

                  const SizedBox(height: 20),
                  const Divider(),
                  const Text("Manual Tuning"),

                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                    children: [
                      ElevatedButton(
                        onPressed: () => _confirmAndCmd(
                          'set_home_position',
                          'Set Home',
                          'Are you sure you want to reset the Home Position to 0 here?',
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.orange,
                        ),
                        child: const Text(
                          "Set Home",
                          style: TextStyle(color: Colors.white),
                        ),
                      ),
                      ElevatedButton(
                        onPressed: () => _confirmAndCmd(
                          'set_extend_position',
                          'Set Extend Limit',
                          'Are you sure you want to save this as the Maximum Extend Limit?',
                        ),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.green,
                        ),
                        child: const Text(
                          "Set Extend",
                          style: TextStyle(color: Colors.white),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),

                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      color: Colors.grey.withValues(alpha: 0.1),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Column(
                      children: [
                        IconButton(
                          icon: const Icon(Icons.arrow_upward, size: 40),
                          onPressed: () => _cmd('move_forward'),
                        ),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.turn_left, size: 40),
                              onPressed: () => _cmd('turn_left'),
                            ),
                            const SizedBox(width: 20),
                            IconButton(
                              icon: const Icon(
                                Icons.stop_circle,
                                size: 50,
                                color: Colors.red,
                              ),
                              onPressed: () => _cmd('stop'),
                            ),
                            const SizedBox(width: 20),
                            IconButton(
                              icon: const Icon(Icons.turn_right, size: 40),
                              onPressed: () => _cmd('turn_right'),
                            ),
                          ],
                        ),
                        IconButton(
                          icon: const Icon(Icons.arrow_downward, size: 40),
                          onPressed: () => _cmd('move_backward'),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// Profile Page
class ProfilePage extends StatelessWidget {
  const ProfilePage({super.key});

  Future<void> _cmd(String c, BuildContext ctx) async {
    await FirebaseFirestore.instance
        .collection('control')
        .doc('motor_command')
        .set({'command': c, 'timestamp': FieldValue.serverTimestamp()});
  }

  Future<void> _confirmAndCmd(
    BuildContext ctx,
    String cmd,
    String title,
    String content,
  ) async {
    final bool? confirm = await showDialog<bool>(
      context: ctx,
      builder: (BuildContext context) {
        return AlertDialog(
          title: Text(title),
          content: Text(content),
          actions: <Widget>[
            TextButton(
              child: const Text("Cancel"),
              onPressed: () => Navigator.of(context).pop(false),
            ),
            TextButton(
              child: const Text("Confirm"),
              onPressed: () => Navigator.of(context).pop(true),
            ),
          ],
        );
      },
    );

    if (confirm == true) {
      await _cmd(cmd, ctx);

      await FirebaseFirestore.instance.collection('system_events').add({
        'message': 'User Action: $title',
        'timestamp': FieldValue.serverTimestamp(),
      });

      if (ctx.mounted) {
        ScaffoldMessenger.of(
          ctx,
        ).showSnackBar(SnackBar(content: Text("$title Command Sent!")));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final user = FirebaseAuth.instance.currentUser;
    final theme = Provider.of<ThemeProvider>(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          ListTile(
            leading: const Icon(Icons.person, size: 40),
            title: Text(user?.email ?? "User"),
            subtitle: const Text("Administrator"),
          ),
          const Divider(),
          SwitchListTile(
            title: const Text("Dark Mode"),
            value: theme.isDarkMode,
            onChanged: (v) => theme.toggleTheme(v),
            secondary: const Icon(Icons.dark_mode),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.home),
            title: const Text('Set Home Position'),
            subtitle: const Text('Reset encoders to 0'),
            trailing: ElevatedButton(
              onPressed: () => _confirmAndCmd(
                context,
                'set_home_position',
                'Set Home',
                'Are you sure you want to reset the Home Position to 0 here?',
              ),
              child: const Text("Set"),
            ),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.flag),
            title: const Text('Set Extend Limit'),
            subtitle: const Text('Save current position as max'),
            trailing: ElevatedButton(
              onPressed: () => _confirmAndCmd(
                context,
                'set_extend_position',
                'Set Extend Limit',
                'Are you sure you want to save this as the Maximum Extend Limit?',
              ),
              child: const Text("Set"),
            ),
          ),
          const Divider(),
          const SizedBox(height: 20),
          ElevatedButton(
            onPressed: () => FirebaseAuth.instance.signOut(),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.red,
              foregroundColor: Colors.white,
            ),
            child: const Text("Logout"),
          ),
        ],
      ),
    );
  }
}

// Login Screen
class LoginRegisterScreen extends StatefulWidget {
  const LoginRegisterScreen({super.key});
  @override
  State<LoginRegisterScreen> createState() => _LoginRegisterScreenState();
}

class _LoginRegisterScreenState extends State<LoginRegisterScreen> {
  final _email = TextEditingController();
  final _pass = TextEditingController();
  bool _isLogin = true;

  Future<void> _submit() async {
    try {
      if (_isLogin) {
        await FirebaseAuth.instance.signInWithEmailAndPassword(
          email: _email.text.trim(),
          password: _pass.text.trim(),
        );
      } else {
        await FirebaseAuth.instance.createUserWithEmailAndPassword(
          email: _email.text.trim(),
          password: _pass.text.trim(),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text("Error: $e")));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              _isLogin ? "Smart Rack Login" : "Register",
              style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 20),
            TextField(
              controller: _email,
              decoration: const InputDecoration(
                labelText: "Email",
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _pass,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: "Password",
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _submit,
              child: Text(_isLogin ? "Login" : "Register"),
            ),
            TextButton(
              onPressed: () => setState(() => _isLogin = !_isLogin),
              child: Text(_isLogin ? "Create Account" : "Have Account?"),
            ),
          ],
        ),
      ),
    );
  }
}