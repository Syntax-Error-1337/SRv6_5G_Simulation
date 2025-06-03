# sdn_controller/my_ml_controller.py

import os
import sys
import random # For dynamic dummy data

# --- 1. Ensure Python can find the src directory ---
# Get the directory containing this script (sdn_controller)
controller_dir = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (Repo root)
repo_root = os.path.dirname(controller_dir)
# Construct the absolute path to the 'src' directory
src_path = os.path.join(repo_root, 'src')
# Add the 'src' directory to Python's search path (sys.path)
if src_path not in sys.path:
    sys.path.insert(0, src_path) # Insert at the beginning for higher priority

# --- Now we can import modules from src ---
try:
    # Since src is in sys.path, we can directly import from the 'ml' package
    from ml.predict_path import PathPredictor
except ImportError as e:
    print(f"Error importing PathPredictor: {e}")
    print(f"Ensure 'predict_path.py' exists in '{os.path.join(src_path, 'ml')}'")
    sys.exit(1)

# --- 2. Set paths for models and config files (relative to Repo root) ---
# NOTE: Ensure your model files (rf_model.pkl, lstm_model.keras, gru_model.keras)
# are in the location specified by MODEL_DIR (e.g., repo root or a 'data/' folder).
# Adjust MODEL_DIR if your models are saved elsewhere by main.py.
MODEL_DIR = repo_root # Assuming models are in the repo root for now
CONFIG_DIR = os.path.join(repo_root, 'configs')

RF_MODEL_PATH = os.path.join(MODEL_DIR, 'rf_model.pkl')
LSTM_MODEL_PATH = os.path.join(MODEL_DIR, 'lstm_model.keras')
GRU_MODEL_PATH = os.path.join(MODEL_DIR, 'gru_model.keras')
TRAFFIC_CONFIG_PATH = os.path.join(CONFIG_DIR, 'traffic_profiles.yaml')

# --- 3. Import Ryu related modules ---
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib import hub # Ryu's GreenThread library for background tasks

# --- 4. Example validation loss values (you should use values from actual training) ---
# These values affect the weighting in model ensembling. Replace with real values if available.
# If you regenerate models, main.py calculates these. For now, placeholders are fine.
EXAMPLE_LSTM_VAL_LOSS = 0.1 # Placeholder, get actual value if possible
EXAMPLE_GRU_VAL_LOSS = 0.1  # Placeholder, get actual value if possible

class MyMlController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(MyMlController, self).__init__(*args, **kwargs)
        self.topology_api_app = self # For topology discovery later
        self.predictor = None       # To hold the PathPredictor instance
        self.logger.info("My ML Controller Initializing...")

        # Define the slice types to simulate optimization for, in a cycle
        # You can get these from your 'configs/traffic_profiles.yaml' keys
        # Or from the 'slices' list in your main.py
        self.slice_types_to_simulate = [
            'eMBB', 'URLLC', 'mMTC', 'video_streaming', 'game_streaming',
            'metaverse', 'iot', 'ar_vr', 'autonomous_vehicles',
            'smart_grid', 'healthcare_monitoring'
        ] # Using the list from your main.py
        self.current_slice_index = 0 # To track the current slice type in the cycle

        # --- 5. Load ML models and PathPredictor ---
        try:
            self.logger.info("Loading ML models and PathPredictor...")
            required_files = [RF_MODEL_PATH, LSTM_MODEL_PATH, GRU_MODEL_PATH, TRAFFIC_CONFIG_PATH]
            for f_path in required_files:
                if not os.path.exists(f_path):
                     raise FileNotFoundError(f"Required file not found: {f_path}. "
                                             "Please ensure models are generated (e.g., by running main.py) "
                                             "and paths in my_ml_controller.py are correct.")

            self.predictor = PathPredictor(
                rf_model_path=RF_MODEL_PATH,
                lstm_model_path=LSTM_MODEL_PATH,
                gru_model_path=GRU_MODEL_PATH,
                traffic_config_path=TRAFFIC_CONFIG_PATH,
                lstm_val_loss=EXAMPLE_LSTM_VAL_LOSS,
                gru_val_loss=EXAMPLE_GRU_VAL_LOSS
            )
            self.logger.info("PathPredictor loaded successfully.")
        except FileNotFoundError as e:
             self.logger.error(f"Initialization failed: {e}")
             self.predictor = None
        except Exception as e:
            self.logger.error(f"Error loading PathPredictor: {e}", exc_info=True)
            self.predictor = None

        # --- 6. Start a background task for periodic prediction ---
        if self.predictor:
            self.monitor_thread = hub.spawn(self._monitor)
            self.logger.info("Monitor thread started.")
        else:
            self.logger.warning("Predictor not loaded, so the monitor thread was not started.")

    def _monitor(self):
        """Background task that periodically triggers path prediction for different slice types."""
        self.logger.info("Monitor task running...")
        while True:
            # Determine which slice type to optimize for in this iteration
            target_slice = self.slice_types_to_simulate[self.current_slice_index]
            self.logger.info(f"Monitor loop iteration. Optimizing for SLICE: {target_slice}")

            self._perform_prediction_for_slice(target_slice)

            # Move to the next slice type for the next iteration
            self.current_slice_index = (self.current_slice_index + 1) % len(self.slice_types_to_simulate)
            
            hub.sleep(10) # Wait for 10 seconds before the next prediction cycle

    def _generate_candidate_path_metrics(self, path_id_prefix: str, slice_type_for_paths: str, num_paths: int) -> list:
        """
        Helper function: Generates 'num_paths' candidate paths with dummy metrics
        for the given 'slice_type_for_paths'.
        """
        candidate_metrics_list = []
        for i in range(num_paths):
            # Base random values
            delay_val = random.uniform(5.0, 50.0)
            packet_loss_val = random.uniform(0.0, 0.05) # Percentage (0.0 to 1.0)
            throughput_val = random.uniform(100.0, 1000.0) # Mbps
            qos_violations_val = random.choice([0, 1, 2])
            jitter_val = random.uniform(0.1 * delay_val, 0.3 * delay_val) # Jitter often related to delay
            latency_variance_val = random.uniform(0.1, delay_val / 2) # Latency variance

            # Adjust random metric ranges based on slice_type_for_paths to make data more representative
            if slice_type_for_paths == 'URLLC':
                delay_val = random.uniform(1.0, 10.0)        # Lower delay for URLLC
                packet_loss_val = random.uniform(0.0, 0.001) # Very low packet loss for URLLC
                throughput_val = random.uniform(50.0, 300.0) # Throughput might be less critical for some URLLC
                qos_violations_val = random.choice([0, 1])
                jitter_val = random.uniform(0.1, 0.5 * delay_val)
                latency_variance_val = random.uniform(0.01, 0.3 * delay_val)
            elif slice_type_for_paths == 'eMBB':
                delay_val = random.uniform(10.0, 80.0)       # Higher delay tolerance for eMBB
                packet_loss_val = random.uniform(0.001, 0.02)
                throughput_val = random.uniform(500.0, 2000.0) # High throughput for eMBB
            elif slice_type_for_paths == 'mMTC':
                delay_val = random.uniform(50.0, 200.0)      # mMTC can tolerate high delay
                packet_loss_val = random.uniform(0.01, 0.1)
                throughput_val = random.uniform(1.0, 50.0)   # Low throughput for mMTC
                qos_violations_val = random.choice([0, 1, 2, 3])
            # Add more 'elif' blocks here for other slice types in self.slice_types_to_simulate
            # to fine-tune their typical metric ranges for dummy data.

            candidate_metrics_list.append({
              'delay': delay_val,
              'jitter': jitter_val,
              'packet_loss': packet_loss_val,
              'throughput': throughput_val,
              'latency_variance': latency_variance_val,
              'reliability': random.uniform(0.95, 0.9999), # General reliability
              'avg_congestion': random.uniform(0.01, 0.6),  # Average congestion
              'qos_violations': qos_violations_val,
              'path_id': f'{path_id_prefix}_path_{i+1}',
              'slice_type': slice_type_for_paths, # CRITICAL: All candidates for this call have this slice type
              'routing_type': 'SRv6'
            })
        return candidate_metrics_list

    def _perform_prediction_for_slice(self, target_slice_type: str):
        """
        Performs path prediction specifically for the 'target_slice_type'.
        """
        if not self.predictor:
            self.logger.warning("Predictor is not available, skipping prediction.")
            return

        self.logger.info(f"Performing prediction for SLICE: {target_slice_type} using dynamic dummy data...")

        # Generate, for example, 3 candidate paths, all intended for the target_slice_type
        # The metrics for these paths will be generated by _generate_candidate_path_metrics
        dummy_metrics_list = self._generate_candidate_path_metrics(
            path_id_prefix=f"candidate_for_{target_slice_type}", # Unique ID prefix
            slice_type_for_paths=target_slice_type,
            num_paths=3 # You can change the number of candidate paths
        )

        if not dummy_metrics_list:
            self.logger.warning(f"No candidate paths generated for slice {target_slice_type}.")
            return

        try:
            # Call the prediction function; time_steps defaults to 1 in PathPredictor
            best_path_info = self.predictor.predict_best_path(dummy_metrics_list)

            # Process the prediction result
            if best_path_info and best_path_info.get('path_id') != 'none':
                # The best_path_info['slice_type'] should match target_slice_type
                # because all candidates belonged to that slice.
                self.logger.info(f"Prediction Result for SLICE OPTIMIZATION TARGET [{target_slice_type}]:\n"
                                 f"  Chosen Path ID: '{best_path_info['path_id']}'\n"
                                 f"  Path's Original Slice Type: '{best_path_info.get('slice_type')}' (Should be {target_slice_type})\n"
                                 f"  Score: {best_path_info.get('score', 'N/A'):.2f}\n"
                                 f"  Metrics -- Delay: {best_path_info.get('metrics', {}).get('delay', 'N/A'):.2f} ms, "
                                 f"Loss: {best_path_info.get('metrics', {}).get('packet_loss', 'N/A'):.4f}, "
                                 f"Throughput: {best_path_info.get('metrics', {}).get('throughput', 'N/A'):.2f} Mbps")
            else:
                self.logger.warning(f"Prediction for slice {target_slice_type} returned no best path or an error condition.")

        except Exception as e:
            self.logger.error(f"Error during prediction for slice {target_slice_type}: {e}", exc_info=True)

    # --- Ryu Event Handlers (basic setup for now, will be expanded later) ---
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handle switch features event when a switch connects."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.logger.info(f"Switch connected: {datapath.id:016x}") # Log switch DPID

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, datapath, priority, match, actions):
        """Helper function to add a flow entry to the switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                match=match, instructions=inst)
        datapath.send_msg(mod)
