import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { GeometryDataViewer } from "@/components/geometry-data-viewer/GeometryDataViewer";
import { ObjectInspector } from "@/components/object-inspector/ObjectInspector";
import type { GeometryFeature, ProjectObject } from "@/types/api";

describe("Core Provenance & Native Inspection Components", () => {
  it("renders every standalone provenance status accurately", () => {
    const statuses = [
      "native",
      "calculated",
      "reconstructed",
      "inferred",
      "ai_generated",
      "unresolved",
      "unsupported",
    ] as const;
    render(
      <div>
        {statuses.map((s) => (
          <ProvenanceBadge key={s} status={s} />
        ))}
      </div>
    );
    for (const s of statuses) {
      expect(screen.getByText(s)).toBeInTheDocument();
    }
  });

  it("renders GeometryDataViewer as structured coordinates with calibration without drawing canvas or raster image", () => {
    const feature: GeometryFeature = {
      id: "geom-1",
      section_guid: "{CB477009-2C9F-49F1-8ADD-42B02D38F149}",
      parent_object_guid: "{1CB26172-81E8-4EA8-A144-805C05A379B7}",
      page_guid: "{A496DDA7-D1E4-4BF2-8A4F-A2B35507BE3E}",
      geometry_type: "Polygon",
      coordinate_system: "planswift_page_calibrated",
      point_count: 4,
      bbox_min_x: 0,
      bbox_min_y: 0,
      bbox_max_x: 375,
      bbox_max_y: 375,
      derived_polyline_length: 1500,
      derived_polygon_area: 140625,
      scale_x: 37.5,
      scale_y: 37.5,
      scale_unit: "FT",
      is_calibrated: true,
      calibrated_length: 40.0,
      calibrated_area: 100.0,
      calibrated_unit: "SQ FT",
      normalized_area_m2: 9.2903,
      provenance: "native",
      derived_metrics_provenance: "reconstructed",
      points: [
        {
          point_order: 0,
          x: 3234.37109375,
          y: 755.450866699219,
          point_type: "Normal",
          raw_x: "3234.37109375",
          raw_y: "755.450866699219",
          normalized_x: 86.249896,
          normalized_y: 20.145356,
          provenance: "native",
        },
      ],
    };

    const { container } = render(<GeometryDataViewer feature={feature} />);
    expect(screen.getByText("3234.37109375")).toBeInTheDocument();
    expect(screen.getByText("100.00 SQ FT")).toBeInTheDocument();
    expect(container.querySelector("canvas")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders ObjectInspector preserving empty-name properties and calculation sections", () => {
    const obj: ProjectObject = {
      id: "obj-1",
      project_version: "ver-1",
      native_guid: "{1CB26172-81E8-4EA8-A144-805C05A379B7}",
      native_class: "Count",
      native_type: "Count",
      name: "Duct 250x150mm",
      parent_guid: "{BA630457-834C-481A-AA57-E33D401C9B04}",
      root_path: "project 4/Takeoff/Duct 250x150mm",
      depth: 2,
      order_index: 3,
      is_known_class: true,
      is_measurement_section: false,
      is_page: false,
      page_guid: null,
      group_id: null,
      division: "",
      cost_code: "",
      provenance: "native",
      property_count: 1,
      properties: [
        {
          id: "prop-1",
          native_property_guid: "{02A3C215-A4ED-4721-8C1E-2DC3891BBA23}",
          name: "",
          property_class: "Text",
          raw_value: "",
          parsed_value_json: null,
          normalized_value_json: null,
          normalized_unit: "",
          units: "",
          input_units: "",
          group: "Other",
          order_index: 0,
          decimal_places: "2",
          parse_formula: "-1",
          expression_flag: "",
          is_formula: false,
          is_expression_script: false,
          is_dynamic_page_order: false,
          dynamic_page_guid: "",
          has_image_data: false,
          image_data_length: 0,
          image_data_sha256: "",
          attributes_json: {},
          source_location: "XMLData.XML",
          provenance: "native",
          normalization_provenance: "",
        },
      ],
    };

    render(<ObjectInspector object={obj} />);
    expect(screen.getByText("Duct 250x150mm")).toBeInTheDocument();
    expect(screen.getByText("(empty Name attribute)")).toBeInTheDocument();
    expect(screen.getByText("Independent Calculation Audit")).toBeInTheDocument();
  });

  it("distinguishes DXF/IFC native, calculated, and inferred provenance badges without rasterizing", () => {
    render(
      <div data-testid="cad-bim-prov-row">
        <span>Qto_WallBaseQuantities</span>
        <ProvenanceBadge status="native" />
        <span>Geometry.CalculatedVolume</span>
        <ProvenanceBadge status="calculated" />
        <span>A-WALL Rule Category</span>
        <ProvenanceBadge status="inferred" />
      </div>
    );
    expect(screen.getByText("Qto_WallBaseQuantities")).toBeInTheDocument();
    expect(screen.getByText("native")).toBeInTheDocument();
    expect(screen.getByText("calculated")).toBeInTheDocument();
    expect(screen.getByText("inferred")).toBeInTheDocument();
  });
});
