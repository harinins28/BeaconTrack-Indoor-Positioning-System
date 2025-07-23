import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import matplotlib.animation as animation
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib

matplotlib.use("TkAgg")

# Global variables
fig = None
ax = None
on_close_callback = None

# Colors for different tags
TAG_COLORS = ['red', 'blue', 'green', 'orange', 'purple', 'cyan', 'magenta', 'yellow']

def set_on_close(callback):
    global on_close_callback
    on_close_callback = callback

def animate(base_stations, initial_pos, get_updated_data, interval=1000):
    global fig, ax

    # Create the figure and subplot
    fig, ax = plt.subplots(figsize=(10, 10))
    fig.canvas.mpl_connect('close_event', handle_close)

    # Set up the initial plot
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_xlabel('X position (meters)')
    ax.set_ylabel('Y position (meters)')
    ax.set_title('Indoor Positioning System')
    ax.grid(True)

    # Plot base stations
    for i, station in enumerate(base_stations):
        x, y = station["coords"]
        ax.plot(x, y, 'bo', markersize=10, label=f'Base Station {i+1}' if i == 0 else None)
        ax.text(x, y+0.1, f'BS{i+1}', fontsize=8)
        
        # Draw circle for the estimated distance
        circle = patches.Circle((x, y), station["distance"], fill=False, color='green', alpha=0.3)
        ax.add_patch(circle)

    # Dictionary to store position markers for each tag
    position_markers = {}
    position_trails = {}
    distance_circles = {}
    
    # Create initial tag marker and trail
    x, y = initial_pos
    for i, color in enumerate(TAG_COLORS):
        # Create a marker that will be invisible initially - FIX: separate marker and color
        marker, = ax.plot([], [], 'o', color=color, markersize=10, label=f'Tag {i+1}')
        position_markers[i] = marker
        
        # Create a trail line that will be invisible initially - FIX: separate line style and color
        trail, = ax.plot([], [], '-', color=color, alpha=0.5)
        position_trails[i] = trail
        
        # Store circles for distances (3 per tag)
        distance_circles[i] = [None, None, None]

    # Add legend
    ax.legend(loc='upper right')

    def update(frame):
        # Get updated data: base stations, position, receiver data, and tag positions
        base_stations_data, _, receiver_1_data, receiver_2_data, receiver_3_data, all_tag_positions = get_updated_data()
        
        # Update circles for base stations
        for i, station in enumerate(base_stations_data):
            # Remove old circle if it exists
            circle = patches.Circle(
                station["coords"], 
                station["distance"], 
                fill=False,  
                color='green', 
                alpha=0.3
            )
            
            # Remove previous circle if it exists
            for patch in ax.patches:
                if isinstance(patch, patches.Circle) and patch.center == station["coords"]:
                    patch.remove()
                    
            # Add new circle
            ax.add_patch(circle)
        
        # Update position for each tag
        for i, (tag_mac, position) in enumerate(all_tag_positions.items()):
            if i >= len(TAG_COLORS):
                # Skip if we run out of colors
                continue
                
            x, y = position
            
            # Get the marker and trail for this tag
            marker = position_markers[i]
            trail = position_trails[i]
            
            # Update marker position
            marker.set_data([x], [y])
            
            # Update trail
            # Get existing trail data and add new position
            trail_x, trail_y = trail.get_data()
            trail_x = list(trail_x) + [x]
            trail_y = list(trail_y) + [y]
            
            # Limit trail length to avoid cluttering
            max_trail_length = 20
            if len(trail_x) > max_trail_length:
                trail_x = trail_x[-max_trail_length:]
                trail_y = trail_y[-max_trail_length:]
                
            trail.set_data(trail_x, trail_y)
        
        # Make unused markers and trails invisible
        for i in range(len(all_tag_positions), len(TAG_COLORS)):
            position_markers[i].set_data([], [])
            position_trails[i].set_data([], [])

        return list(position_markers.values()) + list(position_trails.values()) + list(ax.patches)

    # Create animation
    ani = animation.FuncAnimation(fig, update, interval=interval, blit=True)
    plt.tight_layout()
    
    # Show the plot
    plt.show()

def handle_close(evt):
    if on_close_callback:
        on_close_callback(evt)
